#!/bin/bash
#SBATCH --nodes 1                      # Node PER JOB. Apparently this works on MARC
#SBATCH --ntasks-per-node 1            # MPI sense -> just 1.
#SBATCH --cpus-per-task 1              # No more than the number of CPU in a node. CPU <- coeur dans slurm
# #SBATCH --qos=week                     # Echo is authorized to launch week-long job
# #SBATCH --reservationname=COVID19

set -x

cd $DATA_PATH

COVID_SLOT_INDEX=${SLURM_ARRAY_TASK_ID}

echo "***************** LOADING ENVIRONMENT *****************"
module purge
# on marcc this is anaconda3/2022.05 to circumvent anaconda python bug. Otherwise that is just anaconda 
module load anaconda
module load anaconda3/2022.05
conda activate covidSP
# in case conda not found
#source /home/jcblemai/.bashrc
#source ~/miniconda3/etc/profile.d/conda.sh # loading conda in case
#eval "$(conda shell.bash hook)"
which python
which Rscript

# my instruction asks to install aws cli in ~/aws-cli/bin, so adding this to the path
export PATH=~/aws-cli/bin:$PATH
echo "***************** DONE LOADING ENVIRONMENT *****************"


echo "***************** FETCHING RESUME FILES *****************"
### In case of resume, download or move the right files
export LAST_JOB_OUTPUT=$(echo $LAST_JOB_OUTPUT | sed 's/\/$//')
if [ -n "$LAST_JOB_OUTPUT" ]; then  # -n Checks if the length of a string is nonzero --> if LAST_JOB_OUTPUT is not empty, the we download the output from the last job
	if [ $COVID_BLOCK_INDEX -eq 1 ]; then  # always true for slurm submissions
		export RESUME_RUN_INDEX=$COVID_OLD_RUN_INDEX
		echo "RESUME_DISCARD_SEEDING is set to $RESUME_DISCARD_SEEDING"
		if [ $RESUME_DISCARD_SEEDING == "true" ]; then
			export PARQUET_TYPES="spar snpi hpar hnpi"
		else
			export PARQUET_TYPES="seed spar snpi hpar hnpi"
		fi
	else                                 # if we are not in the first block, we need to resume from the last job, with seeding an all.
		export RESUME_RUN_INDEX=$COVID_RUN_INDEX
		export PARQUET_TYPES="seed spar snpi seir hpar hnpi hosp llik"
	fi
	for filetype in $PARQUET_TYPES
	do
		if [ $filetype == "seed" ]; then
			export extension="csv"
		else
			export extension="parquet"
		fi
		for liketype in "global" "chimeric"
		do
			export OUT_FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/$liketype/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX-1,'$filetype','$extension'))")
			if [ $COVID_BLOCK_INDEX -eq 1 ]; then
				export IN_FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$RESUME_RUN_INDEX','$COVID_PREFIX/$RESUME_RUN_INDEX/$liketype/final/',$COVID_SLOT_INDEX,'$filetype','$extension'))")
			else
				export IN_FILENAME=$OUT_FILENAME
			fi
            # either copy from s3 or from the file system
            if [[ $LAST_JOB_OUTPUT == *"s3://"* ]]; then
                aws s3 cp --quiet $LAST_JOB_OUTPUT/$IN_FILENAME $OUT_FILENAME
            else
                # cp does not create directorys, so we make the directories first
                export $OUT_FILENAME_DIR="$(dirname "${OUT_FILENAME}")"
                mkdir -p $OUT_FILENAME_DIR
                cp $LAST_JOB_OUTPUT/$IN_FILENAME $OUT_FILENAME
            fi
		    if [ -f $OUT_FILENAME ]; then
				echo "Copy successful for file of type $filetype ($IN_FILENAME -> $OUT_FILENAME)"
			else
				echo "Could not copy file of type $filetype ($IN_FILENAME -> $OUT_FILENAME)"
				if [ $liktype -eq "global" ]; then
					exit 2
				fi
			fi
		done
	done
	ls -ltr model_output
fi
echo "***************** DONE FETCHING RESUME FILES *****************"

echo "***************** RUNNING inference_slot.R *****************"
export LOG_FILE="$FS_RESULTS_PATH/log_${COVID_RUN_INDEX}_${COVID_SLOT_INDEX}.txt"
echo "Rscript $COVID_PATH/R/scripts/inference_slot.R --config $COVID_CONFIG_PATH   # path to the config file  
                                               --run_id $COVID_RUN_INDEX  # Unique identifier for this run
                                               --scenarios $COVID_SCENARIOS  # name of the intervention to run, or 'all' 
                                               --deathrates $COVID_DEATHRATES  # name of the outcome scenarios to run, or 'all'
                                               --jobs 1  # Number of jobs to run in parallel
                                               --simulations_per_slot $COVID_SIMULATIONS_PER_SLOT # number of simulations to run for this slot
                                               --this_slot $COVID_SLOT_INDEX # id of this slot
                                               --this_block 1 # id of this block
                                               --stoch_traj_flag $COVID_STOCHASTIC # Stochastic SEIR and outcomes trajectories if true
                                               --ground_truth_start $COVID_GT_START # First date to include groundtruth for
                                               --ground_truth_end $COVID_GT_END # First date to include groundtruth fo
                                               --pipepath $COVID_PATH
                                               --python python
                                               --rpath Rscript
                                               --is-resume $COVID_IS_RESUME # Is this run a resume
                                               --is-interactive FALSE # Is this run an interactive run" > $LOG_FILE 2>&1 &

Rscript $COVID_PATH/R/scripts/inference_slot.R -p $COVID_PATH --this_slot $COVID_SLOT_INDEX --config $COVID_CONFIG_PATH --run_id $COVID_RUN_INDEX --scenarios $COVID_SCENARIOS --deathrates $COVID_DEATHRATES --jobs 1 --simulations_per_slot $COVID_SIMULATIONS_PER_SLOT --this_block 1 --stoch_traj_flag $COVID_STOCHASTIC --is-resume $COVID_IS_RESUME --is-interactive FALSE > $LOG_FILE 2>&1
dvc_ret=$?
if [ $dvc_ret -ne 0 ]; then
        echo "Error code returned from inference_main.R: $dvc_ret"
fi
echo "***************** DONE RUNNING inference_slot.R *****************"


echo "***************** UPLOADING RESULT TO S3 (OR NOT) *****************"
## copy to s3 if necessary:
if [ $S3_UPLOAD == "true" ]; then
    for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
    do
        export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/chimeric/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','parquet'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
        for type in "seed"
        do
            export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/chimeric/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','csv'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
        for type in "seed"
        do
            export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','csv'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
        for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
    do
        export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','parquet'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
        for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
    do
        export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/final/', $COVID_SLOT_INDEX,'$type','parquet'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
        for type in "seed"
    do
        export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/final/', $COVID_SLOT_INDEX,'$type','csv'))")
        aws s3 cp --quiet $FILENAME $S3_RESULTS_PATH/$FILENAME
    done
fi
echo "***************** DONE UPLOADING RESULT TO S3 (OR NOT) *****************"


# TODO: MV here ? what to do about integration_dump.pkl e.g ?
echo "***************** COPYING RESULTS TO RESULT DIRECTORY *****************"
for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/chimeric/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','parquet'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
for type in "seed"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/chimeric/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','csv'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
for type in "seed"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','csv'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/intermediate/%09d.'% $COVID_SLOT_INDEX,$COVID_BLOCK_INDEX,'$type','parquet'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
    for type in "seir" "hosp" "llik" "spar" "snpi" "hnpi" "hpar"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/final/', $COVID_SLOT_INDEX,'$type','parquet'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
    for type in "seed"
do
    export FILENAME=$(python -c "from gempyor import file_paths; print(file_paths.create_file_name('$COVID_RUN_INDEX','$COVID_PREFIX/$COVID_RUN_INDEX/global/final/', $COVID_SLOT_INDEX,'$type','csv'))")
    export $OUT_FILENAME_DIR="$(dirname "${FS_RESULTS_PATH}/${FILENAME}")"
    mkdir -p $OUT_FILENAME_DIR
    cp --parents $FILENAME $FS_RESULTS_PATH
done
echo "***************** DONE COPYING RESULTS TO RESULT DIRECTORY *****************"

# TODO: replacement for aws copy here ?

echo "DONE EVERYTHING."

# move all the slurm log files:
# doc: By default both standard output and standard error are directed to the same file. 
#For job arrays, the default file name is "slurm-%A_%a.out", 
# "%A" is replaced by the job ID and "%a" with the array index.
# --> THIS DOES NOT WORK 
#mv slurm-$SLURM_ARRAY_JOB_ID_${SLURM_ARRAY_TASK_ID}.out $FS_RESULTS_PATH/slurm-$SLURM_ARRAY_JOB_ID_${SLURM_ARRAY_TASK_ID}.out


wait
