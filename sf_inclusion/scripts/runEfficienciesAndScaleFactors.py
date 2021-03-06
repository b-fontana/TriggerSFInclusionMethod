# coding: utf-8

_all_ = [ "run_eff_sf_1d", "run_eff_sf_1d_outputs", "run_eff_sf_2d_outputs" ]

import os
import argparse
import ctypes
import numpy as np
from copy import copy

import warnings
warnings.filterwarnings('error', '.*Number of graph points is different than histogram bin.*')

import ROOT
ROOT.gROOT.SetBatch(True)
from ROOT import (
    TCanvas,
    TEfficiency,
    TFile,
    TGraphAsymmErrors,
    TH1D,
    TH2D,
    TLatex,
    TLegend,
    TLine,
    TPad,
)

import sys
sys.path.append( os.path.join(os.environ['CMSSW_BASE'], 'src', 'METTriggerStudies'))
from utils.utils import (
    add_vnames,
    create_single_dir,
    dot_dict,
    get_display_variable_name,
    get_hnames,
    get_key_list,
    get_obj_max_min,
    get_root_object,
    load_binning,
    parse_args,
    print_configuration,
    redraw_border,
    rewrite_cut_string,
    split_vnames,
    apply_equal_bin_width,
    write_trigger_string,
)
from luigi_conf import (
    _2Dpairs,
    _extensions,
    _placeholder_cuts,
    _triggers_map,
)

def paint2d(channel, trig):
    lX1, lX2, lY, lYstep = 0.04, 0.7, 0.96, 0.03
    l = TLatex()
    l.SetNDC()
    l.SetTextFont(72)
    l.SetTextSize(0.03)
    l.SetTextColor(1)

    l.DrawLatex( lX1, lY, trig)
    
    latexChannel = copy(channel)
    latexChannel.replace('mu','#mu')
    latexChannel.replace('tau','#tau_{h}')
    latexChannel.replace('Tau','#tau_{h}')
    l.DrawLatex( lX2, lY, 'Channel: '+latexChannel)



def draw_eff_and_sf_1d(proc, channel, variable, trig,
                   save_names_1D,
                   tprefix, indir, subtag, mc_name, data_name,
                   intersection_str, debug):

    _name = lambda a,b,c,d : a + b + c + d + '.root'

    name_data = os.path.join(indir, _name( tprefix, data_name, '_Sum', subtag ) )
    file_data = TFile.Open(name_data, 'READ')

    name_mc = os.path.join(indir, _name( tprefix, mc_name, '_Sum', subtag ))
    file_mc   = TFile.Open(name_mc, 'READ')

    if debug:
        print('[=debug=] Open files:')
        print('[=debug=]  - Data: {}'.format(name_data))
        print('[=debug=]  - MC: {}'.format(name_mc))
        print('[=debug=]  - Args: proc={proc}, channel={channel}, variable={variable}, trig={trig}'
              .format(proc=proc, channel=channel, variable=variable, trig=trig))
   
    hnames1D = { 'ref':  get_hnames('Ref1D')(channel, variable, trig),
                 'trig': get_hnames('Trig1D')(channel, variable, trig) }
   
    keylist_data = get_key_list(file_data, inherits=['TH1'])
    keylist_mc = get_key_list(file_mc, inherits=['TH1'])
    
    for k in keylist_data:
        if k not in keylist_mc:
            m = 'Histogram {} was present in data but not in MC.\n'.format(k)
            m += 'This is possible, but highly unlikely (based on statistics).\n'
            m += 'Check everything is correct, and .qedit this check if so.\n'
            m += 'Data file: {}\n'.format(name_data)
            m += 'MC file: {}'.format(name_mc)
            raise ValueError(m)
   
    keys_to_remove = []
    for k in keylist_mc:
        if k not in keylist_data:
            histo = get_root_object(k, file_mc)
            stats_cut = 10
            if histo.GetEntries() < stats_cut:
                keys_to_remove.append(k)
            else:
                m = '1D Histogram {} was present in MC but not in data.\n'.format(k)
                m += 'The current statistics cut is {},'.format(stats_cut)
                m += ' but this one had {} events.'.format(histo.GetNbinsX())
                m += 'Check everything is correct, and edit this check if so.'
                raise ValueError(m)
   
    for k in keys_to_remove:
        keylist_mc.remove(k)
    assert(set(keylist_data)==set(keylist_mc))
      
    hdata1D, hmc1D = ({} for _ in range(2))
    hdata1D['ref'] = get_root_object(hnames1D['ref'], file_data)
    hmc1D['ref'] = get_root_object(hnames1D['ref'], file_mc)   
    hdata1D['trig'], hmc1D['trig'] = ({} for _ in range(2))

    for key in keylist_mc:
        restr1 = rewrite_cut_string(hnames1D['trig'], '')
        if key.startswith(restr1):
            hdata1D['trig'][key] = get_root_object(key, file_data)
            hmc1D['trig'][key] = get_root_object(key, file_mc)

            # "solve" TGraphasymmErrors bin skipping when denominator=0
            # see TGraphAsymmErrors::Divide() (the default behaviour is very error prone!)
            # https://root.cern.ch/doc/master/classTGraphAsymmErrors.html#a37a202762b286cf4c7f5d34046be8c0b
            for h1D in (hdata1D,hmc1D):
                for ibin in range(1,h1D['trig'][key].GetNbinsX()+1):
                    if ( h1D['trig'][key].GetBinContent(ibin)==0. and
                         h1D['ref'].GetBinContent(ibin)==0. ):
                        h1D['ref'].SetBinContent(ibin, 1)

    # some triggers or their intersection naturally never fire for some channels
    # example: 'IsoMu24' for the etau channel
    if len(hmc1D['trig']) == 0:
        m = ('WARNING [drawEffAndSF1D]: Trigger {} never '.format(trig) +
             'fired for channel={}, variable={} in MC.'
              .format(variable, channel))
        print(m)
        return
    
    effdata1D, effmc1D = ({} for _ in range(2))
    try:
        for kh, vh in hdata1D['trig'].items():
            effdata1D[kh] = TGraphAsymmErrors( vh, hdata1D['ref'])
        for kh, vh in hmc1D['trig'].items():
            effmc1D[kh] = TGraphAsymmErrors( vh, hmc1D['ref'] )
    except SystemError:
        m = 'There is likely a mismatch in the number of bins.'
        raise RuntimeError(m)

    tmpkey = list(hmc1D['trig'].keys())[0] #they all have the same binning
    nb1D = effmc1D[tmpkey].GetN() 

    up_xedge  = lambda obj, i: obj.GetXaxis().GetBinUpEdge(i)
    low_xedge = lambda obj, i: obj.GetXaxis().GetBinLowEdge(i)
    up_yedge  = lambda obj, i: obj.GetYaxis().GetBinUpEdge(i)
    low_yedge = lambda obj, i: obj.GetYaxis().GetBinLowEdge(i)
    ctr_xedge = lambda obj, i: obj.GetXaxis().GetBinCenter(i)
    ctr_yedge = lambda obj, i: obj.GetYaxis().GetBinCenter(i)
        
    darr = lambda x : np.array(x).astype(dtype=np.double)
    sf1D = {}
    assert len(effdata1D) == len(effmc1D)

    # 1-dimensional
    for (kmc,vmc),(kdata,vdata) in zip(effmc1D.items(),effdata1D.items()):
        assert(kmc == kdata)

        x, y, exu, exd, eyu, eyd = ( dot_dict({'dt': [[] for _ in range(nb1D)],    # data 
                                               'mc': [[] for _ in range(nb1D)],    # MC
                                               'sf': [[] for _ in range(nb1D)] })  # scale factor
                                     for _ in range(6) )

        for i in range(nb1D):
            x.mc[i] = ctypes.c_double(0.)
            y.mc[i] = ctypes.c_double(0.)
            vmc.GetPoint(i, x.mc[i], y.mc[i])
            x.mc[i] = x.mc[i].value
            y.mc[i] = y.mc[i].value

            exu.mc[i] = up_xedge(vmc,i)  - ctr_xedge(vmc,i)
            exd.mc[i] = ctr_xedge(vmc,i) - low_xedge(vmc,i)
            eyu.mc[i] = vmc.GetErrorYhigh(i)
            eyd.mc[i] = vmc.GetErrorYlow(i)
   
            x.dt[i] = ctypes.c_double(0.)
            y.dt[i] = ctypes.c_double(0.)
            vdata.GetPoint(i, x.dt[i], y.dt[i])
            x.dt[i] = x.dt[i].value
            y.dt[i] = y.dt[i].value

            exu.dt[i] = up_xedge(vdata,i)  - ctr_xedge(vdata,i)
            exd.dt[i] = ctr_xedge(vdata,i) - low_xedge(vdata,i)
            eyu.dt[i] = vdata.GetErrorYhigh(i)
            eyd.dt[i] = vdata.GetErrorYlow(i)

            if debug:
                print('X MC: xp[{}] = {} +{}/-{} '
                      .format(i,x.mc[i],exu.mc[i],exd.mc[i]), flush=True)
                print('Y MC: yp[{}] = {} +{}/-{} '
                      .format(i,y.mc[i],eyu.mc[i],eyd.mc[i]), flush=True)
                print('X Data: xp[{}] = {} +{}/-{} '
                      .format(i,x.dt[i],exu.dt[i],exd.dt[i]), flush=True)
                print('Y Data: yp[{}] = {} +{}/-{}'
                      .format(i,y.dt[i],eyu.dt[i],eyd.dt[i]), flush=True)
   
            x.sf[i] = x.mc[i]
            exu.sf[i] = exu.mc[i]
            exd.sf[i] = exd.mc[i]
            assert x.dt[i] == x.mc[i]
            assert exu.dt[i] == exu.mc[i]
            assert exd.dt[i] == exd.mc[i]
   
            try:
                y.sf[i] = y.dt[i] / y.mc[i]
            except ZeroDivisionError:
                print('There was a division by zero!', flush=True)
                y.sf[i] = 0
   
            if y.sf[i] == 0:
                eyu.sf[i] = 0
                eyd.sf[i] = 0
            else:
                eyu.sf[i] = np.sqrt( eyu.mc[i]**2 + eyu.dt[i]**2 )
                eyd.sf[i] = np.sqrt( eyd.mc[i]**2 + eyd.dt[i]**2 )
   
            if debug:
                print('X Scale Factors: xp[{}] = {}'.format(i,x.sf[i]), flush=True)
                print('Y Scale Factors: yp[{}] = {} +{}/-{}'.format(i,y.sf[i],eyu.sf[i],eyd.sf[i]), flush=True)
                print('', flush=True)

        sf1D[kdata] = TGraphAsymmErrors( nb1D, darr(x.sf), darr(y.sf),
                                         darr(exd.sf), darr(exu.sf), darr(eyd.sf), darr(eyu.sf) )
        
    if debug:
        print('[=debug=] 1D Plotting...', flush=True)

    n1dt, n1mc, n1sf = 'Data1D', 'MC1D', 'SF1D'
    for akey in sf1D:
        canvas_name = os.path.basename(save_names_1D[0]).split('.')[0]
        canvas_name = rewrite_cut_string(canvas_name, akey, regex=True)
        canvas = TCanvas( canvas_name, 'canvas', 600, 600 )
        canvas.cd()
         
        pad1 = TPad('pad1', 'pad1', 0, 0.35, 1, 1)
        pad1.SetBottomMargin(0.005)
        pad1.SetLeftMargin(0.2)
        pad1.Draw()
        pad1.cd()

        max1, min1 = get_obj_max_min(effdata1D[akey], is_histo=False)
        max2, min2 = get_obj_max_min(effmc1D[akey],   is_histo=False)
        eff_max = max([ max1, max2 ])
        eff_min = min([ min1, min2 ])
        if eff_max == eff_min:
            eff_max = 1.
            eff_min = 0.

        nbins = effdata1D[akey].GetN()
        axor_info = nbins+1, -1, nbins
        axor_ndiv = 605, 705
        axor = TH2D('axor'+akey,'axor'+akey,
                    axor_info[0], axor_info[1], axor_info[2],
                    100, eff_min-0.1*(eff_max-eff_min), eff_max+0.4*(eff_max-eff_min) )
        axor.GetYaxis().SetTitle('Efficiency')
        axor.GetYaxis().SetNdivisions(axor_ndiv[1])
        axor.GetXaxis().SetLabelOffset(1)
        axor.GetXaxis().SetNdivisions(axor_ndiv[0])
        axor.GetYaxis().SetTitleSize(0.08)
        axor.GetYaxis().SetTitleOffset(.85)
        axor.GetXaxis().SetLabelSize(0.07)
        axor.GetYaxis().SetLabelSize(0.07)
        axor.GetXaxis().SetTickLength(0)
        axor.Draw()

        effdata1D_new = apply_equal_bin_width(effdata1D[akey])
        effmc1D_new = apply_equal_bin_width(effmc1D[akey])

        effdata1D_new.SetLineColor(1)
        effdata1D_new.SetLineWidth(2)
        effdata1D_new.SetMarkerColor(1)
        effdata1D_new.SetMarkerSize(1.3)
        effdata1D_new.SetMarkerStyle(20)
        effdata1D_new.Draw('same p0 e')

        effmc1D_new.SetLineColor(ROOT.kRed)
        effmc1D_new.SetLineWidth(2)
        effmc1D_new.SetMarkerColor(ROOT.kRed)
        effmc1D_new.SetMarkerSize(1.3)
        effmc1D_new.SetMarkerStyle(22)
        effmc1D_new.Draw('same p0')

        pad1.RedrawAxis()
        l = TLine()
        l.SetLineWidth(2)
        padmin = eff_min-0.1*(eff_max-eff_min)
        padmax = eff_max+0.1*(eff_max-eff_min)
        fraction = (padmax-padmin)/45

        for i in range(nbins):
            x = axor.GetXaxis().GetBinLowEdge(i) + 1.5;
            l.DrawLine(x,padmin-fraction,x,padmin+fraction)
        l.DrawLine(x+1,padmin-fraction,x+1,padmin+fraction)

        leg = TLegend(0.77, 0.77, 0.96, 0.87)
        leg.SetFillColor(0)
        leg.SetShadowColor(0)
        leg.SetBorderSize(0)
        leg.SetTextSize(0.05)
        leg.SetFillStyle(0)
        leg.SetTextFont(42)

        leg.AddEntry(effdata1D_new, 'Data', 'p')
        leg.AddEntry(effmc1D_new,   proc,   'p')
        leg.Draw('same')

        redraw_border()

        lX, lY, lYstep = 0.23, 0.84, 0.05
        l = TLatex()
        l.SetNDC()
        l.SetTextFont(72)
        l.SetTextColor(1)

        latexChannel = copy(channel)
        latexChannel.replace('mu','#mu')
        latexChannel.replace('tau','#tau_{h}')
        latexChannel.replace('Tau','#tau_{h}')

        l.DrawLatex( lX, lY, 'Channel: '+latexChannel)
        textrigs = write_trigger_string(trig, intersection_str,
                                        items_per_line=2)
        l.DrawLatex( lX, lY-lYstep, textrigs)

        canvas.cd()
        pad2 = TPad('pad2','pad2',0,0.0,1,0.35)
        pad2.SetTopMargin(0.01)
        pad2.SetBottomMargin(0.4)
        pad2.SetLeftMargin(0.2)
        pad2.Draw()
        pad2.cd()
        pad2.SetGridy()

        if max(y.sf) == min(y.sf):
            max1, min1 = 1.1, -0.1
        else:
            max1, min1 = max(y.sf)+max(eyu.sf),min(y.sf)-max(eyd.sf)

        nbins = effdata1D_new.GetN()
        axor_info = nbins+1, -1, nbins
        axor_ndiv = 605, 705
        axor2 = TH2D( 'axor2'+akey,'axor2'+akey,
                      axor_info[0], axor_info[1], axor_info[2],
                      100, min1-0.1*(max1-min1), max1+0.1*(max1-min1) )
        axor2.GetXaxis().SetNdivisions(axor_ndiv[0])
        axor2.GetYaxis().SetNdivisions(axor_ndiv[1])

        # Change bin labels
        rounding = lambda x: int(x) if 'pt' in variable else round(x, 2)
        for i,elem in enumerate(sf1D[akey].GetX()):
            axor2.GetXaxis().SetBinLabel(i+1, str(rounding(elem-sf1D[akey].GetErrorXlow(i))))
        axor2.GetXaxis().SetBinLabel(i+2, str(rounding(elem+sf1D[akey].GetErrorXlow(i))))

        axor2.GetYaxis().SetLabelSize(0.12)
        axor2.GetXaxis().SetLabelSize(0.18)
        axor2.GetXaxis().SetLabelOffset(0.015)
        axor2.SetTitleSize(0.13,'X')
        axor2.SetTitleSize(0.12,'Y')
        axor2.GetXaxis().SetTitleOffset(1.)
        axor2.GetYaxis().SetTitleOffset(0.5)
        axor2.GetYaxis().SetTitle('Data/MC')
            
        axor2.GetXaxis().SetTitle( get_display_variable_name(channel, variable) )
        axor2.GetXaxis().SetTickLength(0)
        axor2.Draw()

        sf1Dnew = apply_equal_bin_width(sf1D[akey])
        sf1Dnew.SetLineColor(ROOT.kRed)
        sf1Dnew.SetLineWidth(2)
        sf1Dnew.SetMarkerColor(ROOT.kRed)
        sf1Dnew.SetMarkerSize(1.3)
        sf1Dnew.SetMarkerStyle(22)
        sf1Dnew.GetYaxis().SetLabelSize(0.12)
        sf1Dnew.GetXaxis().SetLabelSize(0.12)
        sf1Dnew.GetXaxis().SetTitleSize(0.15)
        sf1Dnew.GetYaxis().SetTitleSize(0.15)
        sf1Dnew.GetXaxis().SetTitleOffset(1.)
        sf1Dnew.GetYaxis().SetTitleOffset(0.45)
        sf1Dnew.GetYaxis().SetTitle('Data/MC')
        sf1Dnew.GetXaxis().SetTitle( get_display_variable_name(channel, variable) )
        sf1Dnew.Draw('same P0')

        pad2.cd()
        l = TLine()
        l.SetLineWidth(2)
        padmin = min1-0.1*(max1-min1)
        padmax = max1+0.1*(max1-min1)
        fraction = (padmax-padmin)/30

        for i in range(nbins):
            x = axor2.GetXaxis().GetBinLowEdge(i) + 1.5;
            l.DrawLine(x,padmin-fraction,x,padmin+fraction)
        l.DrawLine(x+1,padmin-fraction,x+1,padmin+fraction)

        redraw_border()

        for aname in save_names_1D[:-1]:
            _name = rewrite_cut_string(aname, akey, regex=True)
            canvas.SaveAs( _name )

        _name = save_names_1D[-1].replace(args.canvas_prefix, '')
        _name = rewrite_cut_string(_name, akey, regex=True)
        eff_file = TFile.Open(_name, 'RECREATE')
        eff_file.cd()

        effdata1D[akey].SetName(n1dt)
        effdata1D[akey].Write(n1dt)
        effmc1D[akey].SetName(n1mc)
        effmc1D[akey].Write(n1mc)
        sf1D[akey].SetName(n1sf)
        sf1D[akey].Write(n1sf)

    if debug:
        print('[=debug=] 2D Plotting...', flush=True)


def draw_eff_and_sf_2d(proc, channel, joinvars, trig,
                       save_names_2D,
                       tprefix, indir, subtag, mc_name, data_name,
                       intersection_str, debug):
    _name = lambda a,b,c,d : a + b + c + d + '.root'

    name_data = os.path.join(indir, _name( tprefix, data_name, '_Sum', subtag ) )
    print(name_data)
    quit()

    file_data = TFile.Open(name_data, 'READ')

    name_mc = os.path.join(indir, _name( tprefix, mc_name, '_Sum', subtag ))
    file_mc   = TFile.Open(name_mc, 'READ')

    if debug:
        print('[=debug=] Open files:')
        print('[=debug=]  - Data: {}'.format(name_data))
        print('[=debug=]  - MC: {}'.format(name_mc))
        print('[=debug=]  - Args: proc={proc}, channel={channel}'
              .format(proc=proc, channel=channel))
        print('[=debug=]  - Args: joinvars={}, trig_inters={}'
              .format(joinvars, trig))
   
    hnames2D = { 'ref':  get_hnames('Ref2D')(channel, joinvars, trig),
                 'trig': get_hnames('Trig2D')(channel, joinvars, trig) }
   
    keylist_data = get_key_list(file_data, inherits=['TH1'])
    keylist_mc = get_key_list(file_mc, inherits=['TH1'])

    for k in keylist_data:
        if k not in keylist_mc:
            m = 'Histogram {} was present in data but not in MC.\n'.format(k)
            m += 'This is possible, but highly unlikely (based on statistics).\n'
            m += 'Check everything is correct, and .qedit this check if so.\n'
            m += 'Data file: {}\n'.format(name_data)
            m += 'MC file: {}'.format(name_mc)
            raise ValueError(m)
   
    keys_to_remove = []
    for k in keylist_mc:
        if k not in keylist_data:
            histo = get_root_object(k, file_mc)
            stats_cut = 10
            if histo.GetEntries() < stats_cut:
                keys_to_remove.append(k)
            else:
                m = '2D Histogram {} was present in MC but not in data.\n'.format(k)
                m += 'The current statistics cut is {},'.format(stats_cut)
                m += ' but this one had {} events.'.format(histo.GetNbinsX())
                m += 'Check everything is correct, and edit this check if so.'
                raise ValueError(m)
   
    for k in keys_to_remove:
        keylist_mc.remove(k)
    assert(set(keylist_data)==set(keylist_mc))

    hdata2D, hmc2D = ({} for _ in range(2))
    hdata2D['ref'] = get_root_object(hnames2D['ref'], file_data)
    hmc2D['ref'] = get_root_object(hnames2D['ref'], file_mc)   
    hdata2D['trig'], hmc2D['trig'] = ({} for _ in range(2))

    for key in keylist_mc:
        restr2 = rewrite_cut_string(hnames2D['trig'], '')
        if key.startswith(restr2):
            hdata2D['trig'][key] = get_root_object(key, file_data)
            hmc2D['trig'][key] = get_root_object(key, file_mc)

            for h2D in [hdata2D,hmc2D]:
                for ix in range(1,h2D['trig'][key].GetNbinsX()+1):
                    for iy in range(1,h2D['trig'][key].GetNbinsY()+1):
                        if ( h2D['trig'][key].GetBinContent(ix,iy)==0. and
                             h2D['ref'].GetBinContent(ix,iy)==0. ):
                            h2D['ref'].SetBinContent(ix,iy,1)

    # some triggers or their intersection naturally never fire for some channels
    # example: 'IsoMu24' for the etau channel
    if  len(hmc2D['trig']) == 0:
        print('WARNING: Trigger {} never fired for channel {} in MC.'
              .format(trig, channel))
        return
    
    effdata2D, effmc2D = ({} for _ in range(2))
    try:
        for kh, vh in hdata2D['trig'].items():
            effdata2D[kh] = vh.Clone(vh.GetName() + '_' + kh)
            effdata2D[kh].Divide(effdata2D[kh], hdata2D['ref'], 1, 1, "B")

        for kh, vh in hmc2D['trig'].items():
            effmc2D[kh] = vh.Clone(vh.GetName() + '_' + kh)
            effmc2D[kh].Divide(effmc2D[kh], hmc2D['ref'], 1, 1, "B")
            
    except SystemError:
        m = 'There is likely a mismatch in the number of bins.'
        raise RuntimeError(m)

    tmpkey = list(hmc2D['trig'].keys())[0]
    nb2Dx = effmc2D[tmpkey].GetNbinsX()
    nb2Dy = effmc2D[tmpkey].GetNbinsY()
        
    sf2D = {}
    assert len(effdata2D) == len(effmc2D)

    for kh, vh in effdata2D.items():
        sf2D[kh] = vh.Clone(vh.GetName() + '_' + kh)
        sf2D[kh].Sumw2()
        sf2D[kh].Divide(effmc2D[kh])
        
    if debug:
        print('[=debug=] 2D Plotting...', flush=True)

    n2 = ['Data2D', 'MC2D', 'SF2D']
    cnames = [x + '_c' for x in n2]
    ROOT.gStyle.SetPaintTextFormat("4.3f");

    base_name = ( save_names_2D[joinvars][n2[0]][0]
                  .split('.')[0]
                  .replace('EffData_', '')
                  .replace('Canvas2D_', '') )

    hzip = zip(effdata2D.items(), effmc2D.items(), sf2D.items())
    for items in hzip:
        # save 2D histograms
        _name = rewrite_cut_string(base_name, items[0][0], regex=True)
        _name += '.root'

        eff_file_2D = TFile.Open(_name, 'RECREATE')
        eff_file_2D.cd()

        for itype, obj in enumerate(items):
            obj[1].SetName(n2[itype])
            obj[1].Write(n2[itype])
  
            # upper and lower 2D uncertainties
            eff_eu = obj[1].Clone(n2[itype] + '_eu')
            eff_ed = obj[1].Clone(n2[itype] + '_ed')
            for i in range(1,obj[1].GetNbinsX()+1):
                for j in range(1,obj[1].GetNbinsY()+1):
                    abin = obj[1].GetBin(i, j)
                    eu2d = obj[1].GetBinErrorLow(abin)
                    ed2d = obj[1].GetBinErrorUp(abin)
                    if obj[1].GetBinContent(abin)==0.:
                        eff_eu.SetBinContent(abin, 0.)
                        eff_ed.SetBinContent(abin, 0.)
                    else:
                        eff_eu.SetBinContent(abin, eu2d)
                        eff_ed.SetBinContent(abin, ed2d)
      
                    if eff_eu.GetBinContent(abin)==0.:
                        eff_eu.SetBinContent(abin, 1.e-10)
                    if eff_ed.GetBinContent(abin)==0.:
                        eff_ed.SetBinContent(abin, 1.e-10)

            canvas = TCanvas(cnames[itype]+obj[0], cnames[itype]+obj[0], 600, 600)
            canvas.SetLeftMargin(0.10)
            canvas.SetRightMargin(0.15);
            canvas.cd()
      
            vnames_2D = split_vnames(joinvars)
            vname_x = get_display_variable_name(channel, vnames_2D[0])
            vname_y = get_display_variable_name(channel, vnames_2D[1])
            rx = 2 if 'pt' not in vname_x else 0
            ry = 2 if 'pt' not in vname_y else 0
            veff_new = apply_equal_bin_width(obj[1], roundx=rx, roundy=ry)
            veff_new.GetXaxis().SetTitleOffset(1.0)
            veff_new.GetYaxis().SetTitleOffset(1.3)
            veff_new.GetXaxis().SetTitleSize(0.03)
            veff_new.GetYaxis().SetTitleSize(0.03)
            veff_new.GetXaxis().SetLabelSize(0.03)
            veff_new.GetYaxis().SetLabelSize(0.03)
            veff_new.GetXaxis().SetTitle(vname_x)
            veff_new.GetYaxis().SetTitle(vname_y)
            # useful when adding errors
            # check scripts/draw2DTriggerSF.py
            veff_new.SetBarOffset(0.22)
            veff_new.SetMarkerSize(.75)
            veff_new.SetMarkerColor(ROOT.kOrange+10)
            veff_new.SetMarkerSize(.8)
            ROOT.gStyle.SetPaintTextFormat("4.3f");
            veff_new.Draw('colz text')
      
            # numerator and denominator
            if itype == 0: # data
                htot = hdata2D['ref'].Clone('tot')
                hpass = hdata2D['trig'][obj[0]].Clone('pass')
            elif itype == 1: # MC
                htot = hmc2D['ref'].Clone('tot')
                hpass = hmc2D['trig'][obj[0]].Clone('pass')

            if itype < 2:
                htot.SetName('tot_' + str(itype))
                hpass.SetName('pass_' + str(itype))
                htot = apply_equal_bin_width(htot)
                hpass = apply_equal_bin_width(hpass)
                htot.SetMarkerSize(.65)
                hpass.SetMarkerSize(.65)
                htot.SetMarkerColor(ROOT.kOrange+6)
                hpass.SetMarkerColor(ROOT.kOrange+6)
                hpass.SetBarOffset(-0.10)
                htot.SetBarOffset(-0.22)
                ROOT.gStyle.SetPaintTextFormat("4.3f");
                hpass.Draw("same text")
                htot.Draw("same text")
      
            # up and down errors for the 2D histogram
            eff_eu = apply_equal_bin_width(eff_eu)
            eff_ed = apply_equal_bin_width(eff_ed)
            eff_eu.SetMarkerSize(.6)
            eff_ed.SetMarkerSize(.6)
            eff_eu.SetBarOffset(0.323);
            eff_ed.SetBarOffset(0.10);
            eff_eu.SetMarkerColor(ROOT.kBlack)
            eff_ed.SetMarkerColor(ROOT.kBlack)
            ROOT.gStyle.SetPaintTextFormat("+ 4.3f xxx");
            eff_eu.Draw("same text")
            ROOT.gStyle.SetPaintTextFormat("- 4.3f");
            eff_ed.Draw("same text")
      
            lX, lY, lYstep = 0.8, 0.92, 0.045
            l = TLatex()
            l.SetNDC()
            l.SetTextFont(72)
            l.SetTextColor(2)
            textrig = write_trigger_string(trig, intersection_str,
                                           items_per_line=2)
            l.DrawLatex(lX, lY, n2[itype].replace('2D',''))
      
            paint2d(channel, textrig)
            redraw_border()

            for full in save_names_2D[joinvars][n2[itype]]:
                full = rewrite_cut_string(full, obj[0], regex=True)
                full = full.replace('Canvas2D_', '')
                canvas.SaveAs(full)
        
def _get_canvas_name(prefix, proc, chn, var, trig, data_name, subtag):
    """
    A 'XXX' placeholder is added for later replacement by all cuts considered for the same channel, variable and trigger combination.
    Without the placeholder one would have to additionally calculate the number of cuts beforehand, which adds complexity with no major benefit.
    """
    add = proc + '_' + chn + '_' + var + '_TRG_' + trig
    n = prefix + data_name + '_' + add
    n += _placeholder_cuts + subtag
    return n

def run_eff_sf_1d_outputs(outdir, data_name, mc_name,
                       trigger_combination, channels, variables, subtag):
    outputs = [[] for _ in range(len(_extensions))]
    processes = mc_name #CHANGE !!!! IF STUDYING MCs SEPARATELY
  
    for proc in processes:
        for ch in channels:
            for var in variables:
                canvas_name = _get_canvas_name(args.canvas_prefix,
                                               proc, ch, var,
                                               trigger_combination,
                                               data_name, subtag)
                thisbase = os.path.join(outdir, ch, var, '')
                create_single_dir( thisbase )

                for ext,out in zip(_extensions, outputs):
                    _out = os.path.join(thisbase, canvas_name + '.' + ext)
                    out.append(_out)                    

    #join all outputs in the same list
    return sum(outputs, []), _extensions, processes

def run_eff_sf_2d_outputs(outdir, proc, data_name,
                          trigger_combination, channel, subtag,
                          intersection_str, draw_independent_MCs, debug):
    """
    This output function is not ready to be used in the luigi framework.
    It returns the outputs corresponding to a single trigger combination.
    This was done for the sake of simplification.
    """
    outputs = {}
    
    # only running when one of the triggers in the intersection
    # matches one of the triggers specified by the user with `_2Dpairs`
    splits = trigger_combination.split(intersection_str)
    run = any({x in _2Dpairs.keys() for x in splits})

    if run:
        for onetrig in splits:
            if onetrig in _2Dpairs:
                for j in _2Dpairs[onetrig]:
                    vname = add_vnames(j[0],j[1])
                    pref2d = args.canvas_prefix.replace('1', '2')
                    cname = _get_canvas_name(pref2d,
                                             proc, channel, vname,
                                             trigger_combination,
                                             data_name, subtag)

                    outputs[vname] = {}
                    
                    cnames = { 'Data2D': cname.replace(pref2d,'EffData_'),
                               'MC2D': cname.replace(pref2d,'EffMC_'),
                               'SF2D': cname.replace(pref2d,'SF_') }

                    thisbase = os.path.join(outdir, channel, vname, '')

                    create_single_dir(thisbase)

                    for kn,vn in cnames.items():
                        outputs[vname][kn] = []
                        for ext in _extensions:
                            if ext not in ('C', 'root'): #remove extra outputs to reduce noise
                                outputs[vname][kn].append(os.path.join(thisbase, vn + '.' + ext))
    
    if debug:
        for k,out in outputs.items():
            print(k)
            for o in out:
                print(o)
                print()

    return outputs


def run_eff_sf_1d(indir, outdir, data_name, mc_name,
                  trigger_combination, channels, variables, subtag,
                  draw_independent_MCs, tprefix, intersection_str, debug):
    
    outs1D, extensions, processes = run_eff_sf_1d_outputs(outdir,
                                                          mc_name, data_name,
                                                          trigger_combination,
                                                          channels, variables,
                                                          subtag,
                                                          draw_independent_MCs)
  
    dv = len(args.variables)
    dc = len(args.channels) * dv
    dp = len(processes) * dc

    for ip,proc in enumerate(processes):
        for ic,chn in enumerate(channels):
            for iv,var in enumerate(variables):
                index = ip*dc + ic*dv + iv
                names1D = [ outs1D[index + dp*x] for x in range(len(extensions)) ]

                if args.debug:
                    for name in names:
                        print('[=debug=] {}'.format(name))
                        m = ( "process={}, channel={}, variable={}"
                              .format(proc, chn, var) )
                        m += ( ", trigger_combination={}\n"
                               .format(trigger_combination) )
                        print(m)

                drawEffAndSF1D(proc, chn, var,
                               trigger_combination,
                               names1D,
                               tprefix,
                               indir, subtag,
                               mc_name, data_name,
                               intersection_str,
                               debug)

    splits = trigger_combination.split(intersection_str)
    for x in splits:
        if x not in _triggers_map:
            mess = 'Trigger {} was not defined in the configuration.'.format(x)
            raise ValueError(mess)
        
    run = any({x in _2Dpairs for x in splits})
    if run:
        for ip,proc in enumerate(processes):
            for ic,chn in enumerate(channels):
                for onetrig in splits:
                    if onetrig in _2Dpairs:
                        names2D = run_eff_sf_2d_outputs(outdir, proc, data_name,
                                                        trigger_combination,
                                                        chn,
                                                        subtag,
                                                        intersection_str,
                                                        draw_independent_MCs,
                                                        debug)

                        for j in _2Dpairs[onetrig]:
                            vname = add_vnames(j[0],j[1])

                            drawEffAndSF2D(proc, chn, vname,
                                           trigger_combination,
                                           names2D,
                                           tprefix,
                                           indir, subtag,
                                           mc_name, data_name,
                                           intersection_str,
                                           debug)

parser = argparse.ArgumentParser(description='Draw trigger scale factors')
parser.add_argument('--indir', help='Inputs directory', required=True)
parser.add_argument('--outdir', help='Output directory', required=True, )
parser.add_argument('--tprefix', help='prefix to the names of the produceyd outputs (targets in luigi lingo)', required=True)
parser.add_argument('--canvas_prefix', help='canvas prefix', required=True)
parser.add_argument('--subtag', dest='subtag', required=True, help='subtag')
parser.add_argument('--mc_name', dest='mc_name', required=True, nargs='+', type=str,
                    help='MC dataset user names')
parser.add_argument('--data_name', dest='data_name', required=True, nargs='+', type=str,
                    help='Data dataset user names',)
parser.add_argument('--triggercomb', dest='triggercomb', required=True,
                    help='Trigger intersection combination.')
parser.add_argument('--channels',   dest='channels',         required=True, nargs='+', type=str,
                    help='Select the channels over which the workflow will be run.' )
parser.add_argument('--variables',        dest='variables',        required=True, nargs='+', type=str,
                    help='Select the variables over which the workflow will be run.' )
parser.add_argument('--draw_independent_MCs', action='store_true', help='debug verbosity')
parser.add_argument('--intersection_str', dest='intersection_str', required=False, default='_PLUS_',
                    help='String useyd to represent set intersection between triggers.')
parser.add_argument('--debug', action='store_true', help='debug verbosity')
args = parse_args(parser)

ROOT.gStyle.SetOptStat(0)
ROOT.gStyle.SetOptTitle(0)
run_eff_sf_1d(args.indir, args.outdir,
              args.data_name, args.mc_name,
              args.triggercomb,
              args.channels, args.variables,
              args.subtag,
              args.draw_independent_MCs,
              args.tprefix,
              args.intersection_str,
              args.debug)
