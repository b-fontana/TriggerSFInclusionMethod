#!/usr/bin/env bash

### Argument parsing help strings
help_description="prints this help message"
tag_description="select tags"
full_description="also removes HTCondor outputs"
debug_description="debug: prints everything, runs nothing"
function print_usage_workflowClean {
    usage=" $(basename "$0") [-h] [-t -d]: removes folders
where:
    -h / --help  [ ${help_description} ]
    -t / --tag   [ ${tag_description} ]
    -f / --full  [ ${full_description} ]
    -d / --debug [ ${debug_description} ]

    Run example: bash $(basename "$0") -t 000 -t 111 -t 222 -t 654 -f -d
"
    printf "${usage}"
}

### Argument parsing
DEBUG=false
FULL=false
declare -a TAGS;
while [[ $# -gt 0 ]]; do
    key="$1"

    case $key in
	-h|--help)
	    print_usage_workflowClean
	    exit 1
	    ;;	
	-t|--tag)
	    TAGS+=("$2")
	    shift # past argument
	    shift # past value
	    ;;
	-f|--full)
	    FULL=true
	    shift # past argument
	    ;;
	-d|--debug)
	    DEBUG=true
	    shift # past argument
	    ;;
	*)    # unknown option
	    echo "Wrong parameter ${1}."
	    exit 1
	    ;;
    esac
done

### Functions
function list_tags() {
	if [ ${#OLD_TAGS[@]} -eq 1 ]; then
		echo "The following tag is currently available:"
	else
		echo "The following tags are currently available:"
	fi
	for tag in "$@"; do
		echo " - ${tag}"
	done
}

function list_ignored_tags() {
	declare -a tags=( "${@:2}" )
	
	printf "Tags"
	for tag in ${tags[@]}; do
		if [ ${tag} == ${tags[ $((${1}-1)) ]} ]; then
			printf " and '${tag}' "
		elif [ ${tag} == ${tags[0]} ]; then
			printf " '${tag}'"
		else
			printf ", '${tag}'"
		fi
	done
	echo "were ignored since they are not present."
}

### General parameters
BASE_PATH="/data_CMS/cms/alves/TriggerScaleFactors"
EOS_PATH="/eos/home-b/bfontana"

declare -a OLD_TAGS=( $(/bin/ls -1 "${BASE_PATH}") )

# Argument parsing sanity checks
if [[ -z ${TAGS} ]]; then
    echo "Select the tag via the '--tag' option."
    if [ ${#OLD_TAGS[@]} -ne 0 ]; then
		list_tags ${OLD_TAGS[@]}
    else
		echo "No tags are currently available. Everything looks clean!"
    fi
    exit 1;
fi

declare -a REMOVED_TAGS;
for tag1 in ${TAGS[@]}; do
	flag=0
	for tag2 in ${OLD_TAGS[@]}; do
		[[ ${tag1} == ${tag2} ]] && flag=1
	done
	if [ ${flag} -eq 0 ]; then
		REMOVED_TAGS+=( ${tag1} )
	fi
done

# print tags that do not exist and take them out of the list of tags to remove
NREM=${#REMOVED_TAGS[@]}
if [ ${NREM} -eq 1 ]; then
	echo "Tag ${REMOVED_TAGS[1]} was ignored since it is not present."
elif [ ${NREM} -ge 1 ]; then
	list_ignored_tags ${NREM} ${REMOVED_TAGS[@]}
	list_tags ${OLD_TAGS[@]}
fi
for tag in ${REMOVED_TAGS[@]}; do
	TAGS=( ${TAGS[@]/${tag}} ) # remove one element from the array
done

### Argument parsing: information for the user
echo "### Arguments"
echo "TAGS  = ${TAGS[*]}"
echo "DEBUG = ${DEBUG}"
echo "FULL  = ${FULL}"
echo "#############"

### Script main code: remove files
declare -a COMMANDS;
for tag in ${TAGS[@]}; do
	if ${FULL}; then
		COMMANDS+=( "rm -rf ${EOS_PATH}/www/TriggerScaleFactors/${tag}/"
					"rm -rf ${BASE_PATH}/${tag}/"
					"rm -rf jobs/${tag}/" )
	else
		COMMANDS+=( "rm -rf ${BASE_PATH}/${tag}/*root" #hadd outputs
					"rm -rf ${BASE_PATH}/${tag}/targets/DefaultTarget_hadd.txt"
					"rm -rf ${BASE_PATH}/${tag}/targets/DefaultTarget_drawsf.txt"
					"rm -rf jobs/${tag}/" )
	fi
done

for comm in "${COMMANDS[@]}"; do
    if $DEBUG; then
		echo ${comm};
    else
		${comm};
    fi
done;

### final prints
if ${DEBUG}; then
    echo "Debug mode: the files were not removed."
else
    echo "Files removed."
fi

