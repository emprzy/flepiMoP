

# NOTES FOR USER -----------------------------------------------------------
#' 1. Set disease, application, and processing options in the "SETUP" block.
#' 2. Modify submission specifics in the "SUBMISSION SPECIFICS" block for any hub requirements.
#' 3. Be sure to specify if this is a forecast ("fch") or scenario projection ("smh")
#' 4. Make sure the flepiMoP repo (https://github.com/HopkinsIDD/flepiMoP) is in the same directory as this repo

gc()
library(inference)
library(tidyverse)
library(doParallel)




# SETUP -------------------------------------------------------------------

# if using local, make sure its pulled and in same base directory as project
# Use local if no access to internet or making local changes to code
use_local_repo <- TRUE
github_url <- "https://raw.githubusercontent.com/HopkinsIDD/flepiMoP/main"
flepimop_local_dir <- "../flepiMoP"
# flepimop_local_dir <- "../../nCov/flepiMoP"


# ~ Main Run Options -----------------------------------------------------------
pull_gt <- TRUE
full_fit <- FALSE

# ~ Round -----------------------------------------------------------------
round_num <- 3
fch_date <- "Jan15"
config_subname <- "2022_Jan15"

# ~ Application -----------------------------------------------------------
smh_or_fch <- "fch" #"fch" or "smh"
disease <- "flu" # covid19 or flu
repo <- "../../shared/SMH_Flu"
subdir <- NULL  #used for testing purposes

smh_or_fch <- tolower(smh_or_fch)
if(smh_or_fch == "fch"){ subdir <- file.path("FCH", fch_date) }   #"excluding_vacchosp"  #NULL # can be changed to add subanalysis

# ~ Scenarios -------------------------------------------------------------

scenarios <- c("highVE_optImm", "highVE_pesImm", "lowVE_optImm", "lowVE_pesImm") # include all, it will subset later based on what you put in `scenario_num`
scenario_s3_buckets <- c("20221220T173349", "20230115T202608", "20221220T174219", "20221220T174814") # automatically pull from s3 if the data are not local already
override_pull_from_s3 <- c(FALSE, FALSE, FALSE, FALSE) # !!!! VERY IMPORTANT - LEAVE FALSE UNLESS YOU ARE REWRITING THE CURRENT S3 DATA !!!!

scenario_num = 1:4 # which scenarios to process right now
fch_scenario_num = 2
if(tolower(smh_or_fch) == "fch"){
  scenario_num <- fch_scenario_num
}
n_weeks <- 41

# ~ Config Specifics ------------------------------------------------------
subname <- NA
subname_all <- NA

# ~ Outcomes to Include (for processing and plotting) ---------------------------------------------------
outcomes_ <- c("I","C","H","D")
outcomes_time_ <- c("weekly","weekly","weekly","weekly")
outcomes_cum_ <- c(FALSE, FALSE, FALSE, FALSE)

# ~ Calibration -----------------------------------------------------------
outcomes_calibrate = c(FALSE, FALSE, TRUE, FALSE) # match outcomes_
n_calib_days = 14 # need one for each outcome to calibrate

# ~ Other Run Options -----------------------------------------------------
plot_samp <- FALSE
likelihood_prune <- FALSE
likelihood_prune_percentkeep <- 0.1
testing <- FALSE
quick_run <- FALSE
get_vaccination <- FALSE
keep_all_compartments <- FALSE
keep_variant_compartments <- FALSE
keep_vacc_compartments <- FALSE
likelihood_sims <- FALSE








# OTHER SETUP -------------------------------------------------------------

proj_dir <- getwd()


# subset scenarios
if(tolower(smh_or_fch) == "fch"){
  scenario_num <- fch_scenario_num
}
scenarios <- scenarios[scenario_num]
scenario_s3_buckets <- scenario_s3_buckets[scenario_num] # automatically pull from s3 if the data are not local already
override_pull_from_s3 <- override_pull_from_s3[scenario_num] # !!!! VERY IMPORTANT - LEAVE FALSE UNLESS YOU ARE REWRITING THE CURRENT S3 DATA !!!!


geodata_file_path = file.path(config$subpop_setup$geodata)








# SUBMISSION & PROCESSING SPECIFICS ----------------------------------------------------
## -- "outcomes_" are for processing. we want more than we submit for diagnostics.

# Flu Forecasts (FluSight: https://github.com/cdcepi/Flusight-forecast-data/blob/master/data-forecasts/README.md)
if (smh_or_fch == "fch" & disease == "flu"){
    select_submission_targets <- function(data_comb){
        data_comb %>%
            filter(grepl("inc hosp", target)) %>%
            mutate(target = gsub("inc hosp", "inc flu hosp", target)) %>%
            dplyr::select(forecast_date, target_end_date, target, location, type, quantile, value)
    }
    forecast_date_name <- "forecast_date"
    outcomes_ <- c("I","C","H","D")
    outcomes_time_ <- c("weekly","weekly","weekly","weekly")
    outcomes_cum_ <- c(FALSE, FALSE, FALSE, FALSE)
    outcomes_calibrate = c(FALSE, FALSE, TRUE, FALSE)
}

# Flu Projections (Flu SMH: https://github.com/midas-network/flu-scenario-modeling-hub)
if (smh_or_fch == "smh" & disease == "flu"){
    select_submission_targets <- function(data_comb){
        data_comb %>%
            filter(grepl("inc hosp|inc death|cum hosp|cum death|peak size|peak time", target)) %>%
            filter(!(grepl("inc death|cum death", target) & location != "US"))
    }
    forecast_date_name <- "model_projection_date"
    outcomes_ <- c("I","C","H","D")
    outcomes_time_ <- c("weekly","weekly","weekly","weekly")
    outcomes_cum_ <- c(TRUE, TRUE, TRUE, TRUE)
    outcomes_cumfromgt = c(FALSE, FALSE, FALSE, FALSE)
    outcomes_calibrate = c(FALSE, FALSE, TRUE, FALSE)
}

# COVID-19 Forecasts (COVID-19 FCH: https://github.com/reichlab/covid19-forecast-hub/blob/master/data-processed/README.md#Data-formatting)
if (smh_or_fch == "fch" & disease == "covid19"){

    select_submission_targets <- function(data_comb){
        targets <- c(paste0(1:20, " wk ahead cum death"),
                     paste0(1:20, " wk ahead inc death"),
                     paste0(1:8, " wk ahead inc case"),
                     paste0(0:130, " day ahead inc hosp"))

        data_comb <- data_comb %>%
            filter(type != "point-mean" & !(is.na(quantile) & type == "quantile")) %>%
            mutate(quantile = round(quantile, 3)) %>%
            filter(target %in% targets) %>%
            select(-scenario_id, -scenario_name, -forecast_date, -age_group) %>%
            rename(forecast_date = model_projection_date) %>%
            filter(quantile %in% c(0.01, 0.025, seq(0.05, 0.95, by = 0.05), 0.975, 0.99) | is.na(quantile))

        data_comb %>%
          filter(str_detect(target, "inc case")) %>%
          filter(quantile %in% c(0.025, 0.100, 0.250, 0.500, 0.750, 0.900, 0.975) | is.na(quantile)) %>%
          bind_rows(
            data_comb %>% filter(!str_detect(target, "inc case"))) %>%
          mutate(quantile = format(quantile, digits = 3))

    }

    forecast_date_name <- "forecast_date"
    outcomes_ <- c("I","C","H","D")
    outcomes_time_ <- c("weekly","weekly","daily","weekly")
    outcomes_cum_ <- c(FALSE, FALSE, FALSE, TRUE)
    outcomes_cumfromgt = c(FALSE, FALSE, FALSE, TRUE)
    outcomes_calibrate = c(FALSE, FALSE, TRUE, FALSE) # match outcomes_
}

# COVID-19 Projections (COVID-19 SMH: https://github.com/midas-network/covid-scenario-modeling-hub)
if (smh_or_fch == "smh" & disease == "covid19"){
    select_submission_targets <- function(data_comb){
        data_comb %>%
            filter(grepl("inc hosp|inc death|cum hosp|cum death|peak size|peak time", target))
    }
    forecast_date_name <- "model_projection_date"
    outcomes_ <- c("I","C","H","D")
    outcomes_time_ <- c("weekly","weekly","weekly","weekly")
    outcomes_cum_ <- c(TRUE, TRUE, TRUE, TRUE)
    outcomes_cumfromgt = c(FALSE, FALSE, FALSE, FALSE)
    outcomes_calibrate = c(FALSE, FALSE, TRUE, FALSE)
}





# Source Code and Functions -----------------------------------------------

# determine if local repo or pulling from github
# - if local:
#     -- make sure you have the flepiMoP repo in the same base directory as the project directory (i.e., same as COVID19_USA)
#     -- make sure to pull flepiMoP so have most up-to-date
# - if github:
#     -- code is pulled from the https://github.com/HopkinsIDD/flepiMoP repo
#
if (use_local_repo){
    source_loc <- flepimop_local_dir
} else {
    source_loc <- github_url
}
# source("R/process_sims/groundtruth_source.R")
# source("R/process_sims/process_projections_functions_NEW.R")
source(paste0(source_loc, "/postprocessing/groundtruth_source.R"))
source(paste0(source_loc, "/postprocessing/sim_processing_source.R"))






#........................................................................................................


# Get Config for details
config_name <- paste0(paste(na.omit(c("config", toupper(smh_or_fch), paste0("R", round_num), scenarios[1], subname_all[1], config_subname)), collapse="_"), ".yml")
config <- flepicommon::load_config(config_name)

# change n_weeks if FCH (limit to 12 weeks)
projection_date <- lubridate::as_date(config$end_date_groundtruth)+1 # first day after groundtruth cutoff
forecast_date <- lubridate::as_date(config$start_date)+21 # date to start plotting from
end_date <- lubridate::as_date(config$end_date)
validation_date <- lubridate::as_date(config$end_date_groundtruth) # one day before defined forecast date

if (tolower(smh_or_fch)=="fch") {
    n_weeks <- 4
    end_date <- lubridate::as_date(projection_date + n_weeks*7) - 1
}
point_est <- 0.5   # alternative: "mean"
compartment_types = c("vacc","variant","agestrat") # types of compartments, other than standard SEIR
keep_which_compartments <- c("variant") # types of compartments, other than standard SEIR
scenario_ids = paste0(c(LETTERS[1:4]), "-", lubridate::as_date(config$end_date_groundtruth)+1)[scenario_num]
scenario_names <- scenarios
scenarios_all <- scenarios
variants_ <- config$seir$compartments$variant_type
vacc_ <- config$seir$compartments$vaccination_stage
county_level <- FALSE
plot_projections <- TRUE

save_reps <- smh_or_fch=="smh" & !full_fit

# create the repo where everything will be saved
round_directory <- do.call(file.path, as.list(na.omit(c(repo, paste0("R",round_num), subdir))))
dir.create(round_directory, recursive = TRUE, showWarnings = FALSE)
print(round_directory)

# Create Directories for Sim Data
scenario_dir <- file.path(round_directory, scenarios_all)
lapply(scenario_dir, dir.create, recursive = TRUE)





# PULL SIMS FROM S3 -------------------------------------------------------

#check if data have already been pulled
pull_from_s3 <- unlist(lapply(scenario_dir, function(x) length(dir(x)) == 0))
pull_from_s3[override_pull_from_s3] <- TRUE #override and repull if desired

if (any(pull_from_s3)) {

    scen_to_repull <- which(pull_from_s3)
    # library(doParallel)
    # cl <- makeCluster(min(length(scen_to_repull), 2)) # only do 2 at a time otherwise might freeze -- memory intensive
    # registerDoParallel(cl)

    # tmp <- foreach(i=1:length(scen_to_repull), .combine=c) %dopar% {
    for (i in 1:length(scen_to_repull)) {

        scn <- scen_to_repull[i]
        # pull s3 bucket
        sys_call_s3 <- paste0('aws s3 cp --recursive s3://idd-inference-runs/USA-', scenario_s3_buckets[scn], '/model_output/hosp ', scenario_dir[scn], '/hosp --exclude="*" --include="*/final/*"')
        system(sys_call_s3)
    }
    # stopCluster(cl)
}





# LOAD GROUND TRUTH -------------------------------------------------------

Sys.setenv(CONFIG_PATH = config_name)
Sys.setenv(FLEPI_PATH = source_loc)
if (disease == "flu"){
    source(paste0(source_loc, "/datasetup/build_flu_data.R"))
} else if (disease == "covid19"){
    source(paste0(source_loc, "/datasetup/build_covid_data.R"))
}

gt_data <- clean_gt_forplots(readr::read_csv(config$inference$gt_data_path))

if (any(grepl("incidI", colnames(gt_data)))){
  colnames(gt_data) <- gsub("incidI", "incidC", colnames(gt_data))
}
if (any(grepl("cumI", colnames(gt_data)))){
  colnames(gt_data) <- gsub("cumI", "cumC", colnames(gt_data))
}

readr::write_csv(gt_data, file.path(round_directory, "gt_data_clean.csv"))

gc()






# RUN PROCESSING ----------------------------------------------------------

i=1
tmp_out <- list()
n_par <- min(length(scenario_num), 2) # only 2 in parallel so does not crash
n_scn <- length(scenario_num)
cl <- makeCluster(n_par, outfile="")
registerDoParallel(cl)

peak_ram_ <- peakRAM::peakRAM({
    tmp_out <- foreach(i=1:n_scn, .packages=c('tidyverse',"inference"), .combine = "c", .verbose = TRUE) %dopar% {
        # for (i in 1:n_scn) {

        print(i)
        scenario_num <- i
        print(scenarios_all[scenario_num])
        scenario_dir <- paste0(round_directory, "/", scenarios_all[i], "/")

        #source("postprocessing/process_sims_parallel_NEW.R", local=TRUE)
        tmp_out_ <- process_sims(scenario_num = scenario_num,
                                 scenarios_all = scenarios_all,
                                 scenario_names = scenario_names,
                                 scenario_ids = scenario_ids,
                                 proj_id = scenario_names[i],
                                 projection_date = projection_date,
                                 forecast_date = forecast_date,
                                 end_date = end_date,
                                 smh_or_fch = smh_or_fch,
                                 round_num = round_num,
                                 subname_all = subname_all,
                                 config_subname = config_subname,
                                 round_directory = round_directory,
                                 full_fit = full_fit,
                                 testing = testing,
                                 quick_run = quick_run,
                                 outcomes_ = outcomes_,
                                 outcomes_time_ = outcomes_time_,
                                 outcomes_cum_ = outcomes_cum_,
                                 outcomes_cumfromgt = outcomes_cumfromgt,
                                 outcomes_calibrate = outcomes_calibrate,
                                 n_calib_days = n_calib_days,
                                 likelihood_prune = likelihood_prune,
                                 keep_variant_compartments = keep_variant_compartments,
                                 keep_vacc_compartments = keep_vacc_compartments,
                                 keep_all_compartments = keep_all_compartments,
                                 variants_ = variants_,
                                 vacc_ = vacc_,
                                 plot_samp = plot_samp,
                                 gt_data = gt_data,
                                 geodata_file = geodata_file_path,
                                 death_filter = config$outcome_modifiers$scenarios,
                                 summarize_peaks = (smh_or_fch == "smh"),
                                 save_reps = save_reps)
        tmp_out <- list(tmp_out, tmp_out_)
    }
    stopCluster(cl)
    gc()
})

tmp_out
peak_ram_




# COMBINE SCENARIO DATA ---------------------------------------------------

data_comb <- combine_and_format_scenarios(
    config = config,
    round_num = round_num,
    round_directory = round_directory,
    validation_date = validation_date,
    scenarios = scenarios_all,
    projection_date = projection_date,
    forecast_date = forecast_date,
    scenario_ids = scenario_ids,
    full_fit = full_fit,
    forecast_date_name = forecast_date_name)



## TASKS
## - make sure everything else below works
## - Check formatting for submission data and edit if needed




# FINAL SUBMISSION CLEANUP ----------------------------------------------

# Remove unwanted targets & dates
proj_end_date <-config$end_date
data_comb <- data_comb %>% filter(target_end_date <= proj_end_date | (is.na(target_end_date) & target == "peak size hosp")) %>%
  mutate(forecast_date = as.character(forecast_date)) %>%
  distinct()
data_submission <- select_submission_targets(data_comb)

# Check
if(smh_or_fch=='smh'){
  data_submission %>%
    select(scenario_id, scenario_name, target) %>%
    distinct() %>%
    mutate(target = gsub('[[:digit:]]+', '', target)) %>%
    distinct()  %>% print(n=100)
}else{
  data_submission %>%
    select(target) %>%
    distinct() %>%
    mutate(target = gsub('[[:digit:]]+', '', target)) %>%
    distinct()  %>% print(n=100)
}



# SAVE IT
readr::write_csv(data_submission, file.path(round_directory, paste0(lubridate::as_date(ifelse(smh_or_fch=='fch', projection_date, projection_date)), "-JHU_IDD-CovidSP", ifelse(full_fit,"_FULL",""), ".csv")))
arrow::write_parquet(data_submission, file.path(round_directory, paste0(lubridate::as_date(ifelse(smh_or_fch=='fch', projection_date, projection_date)), "-JHU_IDD-CovidSP", ifelse(full_fit,"_FULL",""), ".parquet")))
arrow::write_parquet(data_comb, file.path(round_directory, paste0(projection_date, "-JHU_IDD-CovidSP", ifelse(full_fit,"_FULL",""), "_all.parquet")))

print(paste0("Final data saved in:  [  ", file.path(round_directory, paste0(lubridate::as_date(ifelse(smh_or_fch=='fch', projection_date, projection_date)), "-JHU_IDD-CovidSP", ifelse(full_fit,"_FULL",""), ".csv")), "  ]"))




# ~ Save Replicates Sample ------------------------------------------------

if (!full_fit & smh_or_fch == "smh" & save_reps){

    file_names <- file.path(round_directory, paste0(projection_date, "-JHU_IDD-CovidSP-", scenarios_all, "_100reps.parquet"))
    geodata <- read_csv(geodata_file_path)

    file_samp <- lapply(file_names, arrow::read_parquet)
    file_samp <- data.table::rbindlist(file_samp) %>% as_tibble() %>%
        left_join(geodata %>% select(location = USPS, subpop) %>% add_row(location="US", subpop="US")) %>%
        select(-location) %>%
        mutate(sample = as.integer(sample),
               location = stringr::str_pad(substr(subpop, 1, 2), width=2, side="right", pad = "0")) %>%
        select(-subpop) %>%
        arrange(scenario_id, target_end_date, target, location, age_group)

    file_samp_nums <- file_samp %>%
        select(scenario_id, scenario_name, sample) %>%
        distinct() %>% arrange(scenario_id, sample) %>%
        group_by(scenario_id, scenario_name) %>%
        mutate(sample_new = 1:length(sample)) %>%
        ungroup() %>% as_tibble()

    file_samp <- file_samp %>%
        full_join(file_samp_nums) %>%
        mutate(sample = sample_new) %>% select(-sample_new) %>%
        arrange(scenario_id, target_end_date, target, location, age_group, sample)

    # Remove unwanted targets
    file_samp <- file_samp %>%
        filter(grepl("inc hosp|inc death|cum hosp|cum death", target)) %>%
        filter(!(grepl("inc death|cum death", target) & location != "US"))
    # filter(grepl("inc case|inc hosp|inc death|cum case|cum hosp|cum death", target))

    arrow::write_parquet(file_samp,  file.path(round_directory, paste0(projection_date, "-JHU_IDD-CovidSP", "-sample.parquet")))
}






# CHECKS ------------------------------------------------------------------

# data_submission <- data_submission %>%
#   filter(!grepl("hosp", target))
sum(grepl("hosp", data_submission$target))
length(unique(data_submission$quantile)) #24
length(unique(data_submission$target)) # 6*26 = 156  ## NEW: 8*26 = 208 (incl Infections)
length(unique(data_submission$target))/26 #6 NEW: 8
length(unique(data_submission$target_end_date)) # number of projection weeks
length(unique(data_submission$location)) #52
sort(unique(data_submission$target_end_date))
unique(data_submission$scenario_id)
unique(data_submission$scenario_name)

# check NAs
sum(is.na(data_comb %>% dplyr::select(-quantile)))






# PLOTTING - ALL SCENARIOS -----------------------------------------------------------

if(plot_projections){

    sim_end_date <- lubridate::as_date(projection_date) + (n_weeks*7)-1
    keep_all_compartments <- keep_variant_compartments <- FALSE
    quant_values <- c(0.025, 0.25, 0.75, 0.975) #c(0.25, 0.75)
    quant_names <- paste0(quant_values*100, "%")
    trunc_date <- lubridate::as_date(ifelse(full_fit, lubridate::as_date(forecast_date), lubridate::as_date(projection_date) - 7*10))
    cum_wk_outcomes_ <- outcomes_[outcomes_time_=="weekly" & outcomes_cum_]
    plot_cum <- ifelse(any(outcomes_cum_),TRUE,FALSE)
    plot_incid <- TRUE

    #data input
    data_comb <- arrow::read_parquet(file.path(round_directory, paste0(projection_date, "-JHU_IDD-CovidSP", ifelse(full_fit,"_FULL",""), "_all.parquet")))

    # PDF NAME
    stplot_fname <- file.path(round_directory, paste0(toupper(smh_or_fch), "_all_R",round_num,"_", projection_date,
                                                 ifelse(full_fit, "_FULL",""),
                                                 ifelse(is.na(subname), "", subname)))

    # Run plotting script
    source(paste0(source_loc, "/postprocessing/plot_predictions.R"))
}








# FINAL INFO -----------------------------------------------------------

cat(paste0(
    "disease: ", toupper(disease), "\n",
    "Save Directory: ", round_directory, "\n",
    "SMH/FCH: ", smh_or_fch, "\n",
    "Forecast Date: ", forecast_date, "\n",
    "Projection Date: ", projection_date, "\n",
    "Scenarios: ", paste(scenarios_all, collapse = ", "), "\n",
    "Sub Name: ", subname, "\n",
    "Included: ", paste(c("deaths", "cases", "hosp","inf")[c(TRUE, TRUE, incl_hosp, incl_inf)], collapse = ", "), "\n",
    "Full Fit: ", full_fit, "\n",
    "Quick Run: ", quick_run, "\n",
    "Testing Run: ", testing, "\n",
    "Save File: ", paste0(projection_date, "-JHU_IDD-CovidSP-[SCENARIO]", ifelse(full_fit, "_FULL", ""), ".csv"), "\n"))


print('Processing Complete')



# NOTES:
#  - [process_sims_parallel.R] was previously called [produce_smh_projections_cmprt_parallel.R]
#  - [   ] was previously called produce_smh_projections_cmprt_parallel.R
#  - [   ] was previously called produce_smh_projections_cmprt_parallel.R
#  - [   ] was previously called produce_smh_projections_cmprt_parallel.R




# Export all files generated as a Zip -------------------------------------

dir(round_directory)
files_generated <- dir(round_directory, include.dirs = TRUE, full.names = TRUE)
files_export <- files_generated[!as.logical(rowSums(sapply(X = scenarios_all, FUN = function(x = X) grepl(pattern = x, files_generated))))]
files_export <- files_export[grepl(".parquet|.csv|.pdf", files_export)]
files_export

zip_file_name <- file.path(round_directory, paste(na.omit(c(paste0("R",round_num), gsub("/", "_", subdir))),  collapse = "_"))
# zip(zipfile = zip_file_name,
#     files   = files_export)

dir.create(zip_file_name, recursive = TRUE)
file.copy(from = files_export,
          to = file.path(zip_file_name, basename(files_export)),
          overwrite = TRUE)

# browseURL(paste0(zip_file_name, ".zip"))
# browseURL("/home/shared/SMH/R16/FCH/Jan15/R16_FCH_Jan15.zip")
# browseURL(files_export[1])


# Move to save dir for exporting
setwd(round_directory)
cat(paste0("\n\n",
           "*** TO GET FILES: ***  \n\n",
           "Go to the 'Files' window on the right side of the RStudioServer interface.\n",
           "You should be in the correct directory (", round_directory, ").\n",
           "Check the box next to \n",
           paste0(zip_file_name), ", \ngo to 'More', and click 'Export'.\n",
           "This will download the correct output files to your local computer.\n\n",
           "Make sure to return to your project directory as your working directory `setwd(proj_dir)`\n\n\n"))


# setwd(proj_dir)

