
#' Pipe operator
#'
#' See \code{magrittr::\link[magrittr:pipe]{\%>\%}} for details.
#'
#' @name %>%
#' @rdname pipe
#' @keywords internal
#' @export
#' @importFrom magrittr %>%
#' @usage lhs \%>\% rhs
#' @param lhs A value or the magrittr placeholder.
#' @param rhs A function call using the magrittr semantics.
#' @return The result of calling `rhs(lhs)`.
NULL



load_geodata_file <- function(filename,
                              geoid_len = 0,
                              geoid_pad = "0",
                              state_name = TRUE) {

    if(!file.exists(filename)){stop(paste(filename,"does not exist in",getwd()))}
    geodata <- readr::read_csv(filename) %>%
        dplyr::mutate(geoid = as.character(geoid))

    if (!("geoid" %in% names(geodata))) {
        stop(paste(filename, "does not have a column named geoid"))
    }

    if (geoid_len > 0) {
        geodata$geoid <- stringr::str_pad(geodata$geoid, geoid_len, pad = geoid_pad)
    }

    if(state_name) {
        utils::data(fips_us_county, package = "flepicommon") # arrow::read_parquet("datasetup/usdata/fips_us_county.parquet")
        geodata <- fips_us_county %>%
            dplyr::distinct(state, state_name) %>%
            dplyr::rename(USPS = state) %>%
            dplyr::rename(state = state_name) %>%
            dplyr::mutate(state = dplyr::recode(state, "U.S. Virgin Islands" = "Virgin Islands")) %>%
            dplyr::right_join(geodata)
    }

    return(geodata)
}

##' find_truncnorm_mean_parameter
##'
##' Convenience function that estimates the mean value for a truncnorm distribution given a, b, and sd that will have the expected value of the input mean.
##'
##' @param a lower bound
##' @param b upper bound
##' @param mean desired expected value from truncnorm given a, sd, and sd.
##' @param sd standard deviation
##'
##'
##' @export
##'
find_truncnorm_mean_parameter <- function(a, b, mean, sd) {
    return(
        optim(
            mean,
            purrr::partial(
                function(a, b, mean, sd, x) {
                    abs(truncnorm::etruncnorm(a,b,x,sd) - mean)
                },
                a = a,
                b = b,
                mean = mean,
                sd = sd
            ),
            method = "Brent",
            upper = b + 6 * sd,
            lower = a - 6 * sd
        )$par
    )
}

#' ScenarioHub: Recode scenario hub interventions for "SinglePeriodModifier" method
#'
#' @param data intervention list for the national forecast or the scenariohub
#'
#' @return recoded npi names
#'
#' @export
#'

npi_recode_scenario <- function(data){

    data %>%
        dplyr::mutate(scenario = action,
                      scenario = dplyr::recode(scenario,
                                               "stay at home" = "lockdown",
                                               "stay at home_b" = "lockdown2",
                                               "social distancing" = "sd"),
                      scenario = gsub("reopen_phase", "open_p", scenario),
                      scenario = gsub("reclosure", "close", scenario),
                      scenario = gsub(" ", "", scenario))

}

#'  ScenarioHub: Recode scenario hub interventions for "MultiPeriodModifier" method
#'
#' @param data intervention list for the national forecast or the scenariohub
#'
#' @return recoded npi names for use with MultiPeriodModifier
#' @export
#'

npi_recode_scenario_mult <- function(data){
    data %>% dplyr::mutate(scenario_mult = action_new,
                           scenario_mult = ifelse(grepl("stay at home", scenario_mult), "lockdown", scenario_mult),
                           scenario_mult = gsub("paste", "open_p", scenario_mult),
                           scenario_mult = gsub("phase", "open_p", scenario_mult),
                           scenario_mult = ifelse(grepl("open_p", scenario_mult),
                                                  stringr::str_extract(scenario_mult, "open_p[[:digit:]]+"), scenario_mult),
                           scenario_mult = dplyr::recode(scenario_mult, `social distancing` = "sd"))
}




#' ScenarioHub: Process scenario hub npi list
#'
#' @param intervention_path path to csv with intervention list
#' @param geodata df with state USPS and subpop from load_geodata_file
#' @param prevent_overlap whether to allow for interventions to overlap in time and subpop
#' @param prevent_gaps whether to prevent gaps in interventions (i.e. no interventions)
#'
#' @return df with six columns:
#'         - USPS: state abbreviation
#'         - subpop: county ID
#'         - start_date: intervention start date
#'         - end_date: intervention end date
#'         - name: intervention name
#'         - method: intervention method (e.g. SinglePeriodModifier, MultiPeriodModifier)
#' @export
#'
#' @examples
#' geodata <- load_geodata_file(filename = system.file("extdata", "geodata_territories_2019_statelevel.csv", package = "flepiconfig"))
#' npi_dat <- process_npi_shub(intervention_path = system.file("extdata", "intervention_data.csv", package = "flepiconfig"), geodata)
#'
#' npi_dat
process_npi_usa <- function (intervention_path,
                               geodata,
                               prevent_overlap = TRUE,
                               prevent_gaps = TRUE) {

    og <- readr::read_csv(intervention_path) %>% dplyr::left_join(geodata) %>%
        dplyr::filter(GEOID == "all") %>%
        npi_recode_scenario() %>%
        npi_recode_scenario_mult()

    if (!all(lubridate::is.Date(og$start_date), lubridate::is.Date(og$end_date))) {
        og <- og %>% dplyr::mutate(dplyr::across(tidyselect::ends_with("_date"), ~lubridate::mdy(.x)))
    }
    if ("modifier_method" %in% colnames(og)) {
        og <- og %>% dplyr::mutate(name = dplyr::if_else(modifier_method == "MultiPeriodModifier", scenario_mult, scenario)) %>%
            dplyr::select(USPS, subpop, start_date, end_date, name, modifier_method)
    } else {
        og <- og %>% dplyr::mutate(modifier_method = "MultiPeriodModifier") %>%
            dplyr::select(USPS, subpop, start_date, end_date, name = scenario_mult, modifier_method)
    }
    if (prevent_overlap) {
        og <- og %>% dplyr::group_by(USPS, subpop) %>%
            dplyr::mutate(end_date = dplyr::if_else(end_date >= dplyr::lead(start_date), dplyr::lead(start_date) - 1, end_date))
    }
    if (prevent_gaps) {
        og <- og %>% dplyr::group_by(USPS, subpop) %>%
            dplyr::mutate(end_date = dplyr::if_else(end_date < dplyr::lead(start_date), dplyr::lead(start_date) - 1, end_date))
    }
    return(og)
}



#' Process California intervention data
#'
#' @param intervention_path path to csv with intervention list
#' @param geodata df with state USPS and subpop from load_geodata_file
#' @param prevent_overlap whether to allow for interventions to overlap in time and subpop
#' @param prevent_gaps whether to prevent gaps in interventions (i.e. no interventions)
#'
#' @return df with six columns:
#'         - USPS: state abbreviation
#'         - subpop: county ID
#'         - start_date: intervention start date
#'         - end_date: intervention end date
#'         - name: intervention name
#'         - method: intervention method (e.g. SinglePeriodModifier, MultiPeriodModifier)
#' @export
#'
process_npi_ca <- function(intervention_path,
                           geodata,
                           prevent_overlap = TRUE,
                           prevent_gaps = TRUE,
                           date_format = "%m/%d/%y"
){
    ## read intervention estimates
    og <- readr::read_csv(intervention_path,
                          col_types = list(readr::col_date(format = date_format),
                                           readr::col_character(), readr::col_character(),
                                           readr::col_date(format = date_format), readr::col_character())
                          ) %>%
        dplyr::mutate(subpop = dplyr::if_else(stringr::str_length(subpop)==4, paste0(0, subpop), subpop)) %>%
        dplyr::left_join(geodata) %>%
        dplyr::group_by(county, subpop) %>%
        dplyr::arrange(start_date) %>%
        dplyr::mutate(end_date = dplyr::if_else(is.na(end_date), dplyr::lead(start_date)-1, end_date),
                      end_date = dplyr::if_else(start_date == max(start_date), lubridate::NA_Date_, end_date),
                      method = "MultiPeriodModifier") %>%
        dplyr::ungroup() %>%
        dplyr::select(USPS, subpop, start_date, end_date, name = phase, method)

    if(prevent_overlap){
        og <- og %>%
            dplyr::group_by(USPS, subpop) %>%
            dplyr::mutate(end_date = dplyr::if_else(end_date >= dplyr::lead(start_date) & !is.na(end_date), dplyr::lead(start_date)-1, end_date))
    }

    if(prevent_gaps){
        og <- og %>%
            dplyr::group_by(USPS, subpop) %>%
            dplyr::mutate(end_date = dplyr::if_else(end_date < dplyr::lead(start_date) & !is.na(end_date), dplyr::lead(start_date)-1, end_date))
    }

    return(og)

}

#' Function to process variant data for B117
#'
#' @param variant_path path to variant
#' @param sim_start_date simulation start date
#' @param sim_end_date simulation end date
#' @param month_shift shift in variant growth to earlier if <0 or later >0; defaults to 0
#' @param variant_lb
#' @param varian_effect change in transmission for variant default is 50% from Davies et al 2021

#'
#'
#'
#' @return
#' @examples
#'
#' variant <- generate_variant_b117(variant_path = system.file("extdata", "strain_replace_mmwr.csv", package = "flepiconfig"))
#' variant
#'
#' @export
#'
generate_variant_b117 <- function(variant_path,
                                  sim_start_date=as.Date("2020-03-31"),
                                  sim_end_date=Sys.Date()+60,
                                  month_shift=0,
                                  variant_lb = 1.4,
                                  variant_effect = 1.5
){
    if(is.null(month_shift)){
        month_shift <- 0
    }

    sim_start_date <- as.Date(sim_start_date)
    sim_end_date <- as.Date(sim_end_date)

    strains <- readr::read_csv(variant_path) %>% # TODO: separate functions (options in function @params) to generate variant data
        dplyr::mutate(log_prct_b = log(prct_b), log_prct_b_1m = - 0 - log_prct_b)

    strains <- strains %>%
        dplyr::mutate(logit_prct_b = log(prct_b/(1-prct_b))) %>%
        dplyr::select(-month_b) %>%
        dplyr::mutate(month_a = month_a - month_shift) # shift earlier 0 week


    mL <- drc::drm(prct_b ~ month_a, data = strains, fct = drc::L.3(), type = "continuous")

    # Get impact of strain proportions on R0
    pred_month <- predict(mL, data.frame(month_a=seq(1,12,1)))
    pred_month[pred_month>1] <- 1

    prop_strain_b <- dplyr::tibble(month = 1:12, prop_b = pred_month) %>%
        dplyr::mutate(R_ratio = 1*(1-prop_b) + variant_effect*(prop_b))

    pred_week <- predict(mL, data.frame(month_a=seq(1,13,.23)))
    pred_week[pred_week>1] <- 1

    prop_strain_b_week <- dplyr::tibble(prop_b = pred_week) %>%
        dplyr::mutate(week = 1:nrow(.),
                      R_ratio = 1*(1-prop_b) + variant_effect*prop_b,
                      value_sd = 1*(1-prop_b) + variant_lb*prop_b,
                      value_sd = (R_ratio - value_sd)/1.96)


    prop_strain_b_week <- prop_strain_b_week %>%
        dplyr::mutate(start_date = MMWRweek::MMWRweek2Date(MMWRyear=rep(2021, nrow(.)), MMWRweek=week),
                      end_date = (start_date+6)) %>%
        #mutate(month_abb = tolower(month.abb[lubridate::month(start_date)])) %>%
        dplyr::filter(!(start_date>sim_end_date)) %>%
        dplyr::rowwise() %>%
        dplyr::mutate(end_date = min(end_date, sim_end_date)) %>%
        dplyr::ungroup()

    max_week <- min(prop_strain_b_week %>% dplyr::filter(prop_b==1) %>% dplyr::pull(week))
    variant_data <- prop_strain_b_week %>%
        dplyr::filter(week<=max_week) %>%
        dplyr::mutate(end_date = lubridate::as_date(ifelse(week==max_week, sim_end_date, end_date))) %>%
        dplyr::filter(end_date > sim_start_date) %>%
        dplyr::mutate(start_date = dplyr::if_else(end_date > sim_start_date & start_date < sim_start_date,
                                                  sim_start_date, start_date))

    return(variant_data)

}

#' Function to process variant data for B117/B1617
#'
#' Generate variant interventions
#'
#' @param variant_path_1 path to B117 variant
#' @param variant_path_2 path to B1617 variant
#' @param sim_start_date simulation start date
#' @param sim_end_date simulation end date
#' @param variant_lb
#' @param varian_effect change in transmission for variant default is 50% from Davies et al 2021
#' @param transmission_increase transmission increase in B1617 relative to B117
#'
#'
#' @return
#' @export
#'
#' @examples
#'
#' variant <- generate_multiple_variants(variant_path_1 = system.file("extdata", "B117-fits.csv", package = "flepiconfig"),
#'                                       variant_path_2 = system.file("extdata", "B617-fits.csv", package = "flepiconfig"))
#' variant
#'
generate_multiple_variants <- function(variant_path_1,
                                       variant_path_2,
                                       sim_start_date=as.Date("2020-03-31"),
                                       sim_end_date=Sys.Date()+60,
                                       variant_lb = 1.4,
                                       variant_effect = 1.5,
                                       transmission_increase = 0.2
                                        ){

    if(is.null(transmission_increase)){
        transmission_increase=0.2
    }

    b117 <- readr::read_csv(variant_path_1)
    b1617 <- readr::read_csv(variant_path_2)

    sim_start_date <- as.Date(sim_start_date)
    sim_end_date <- as.Date(sim_end_date)

    b117_week <- b117 %>%
        dplyr::mutate(week = MMWRweek::MMWRweek(date)$MMWRweek,
                      year = MMWRweek::MMWRweek(date)$MMWRyear,
                      start_date = MMWRweek::MMWRweek2Date(MMWRyear=year, MMWRweek=week),
                      end_date = (start_date+6)) %>%
        dplyr::rename(variant_prop = fit) %>%
        dplyr::mutate(variant = "B117") %>%
        dplyr::filter(!(start_date>sim_end_date)) %>%
        dplyr::filter(date==end_date) %>%
        dplyr::mutate(date=start_date) %>%
        dplyr::mutate(param = "ReduceR0") %>%
        dplyr::mutate(R_ratio = 1*(1-variant_prop) + variant_effect*variant_prop
                      # sd_variant = 1*(1-variant_prop) + variant_lb*variant_prop,
                      # sd_variant = (R_ratio - sd_variant)/1.96
                      )

    # B.1.617
    b1617_week <- b1617 %>%
        dplyr::mutate(date = lubridate::mdy(date)) %>%
        dplyr::mutate(week = MMWRweek::MMWRweek(date)$MMWRweek,
                      year = MMWRweek::MMWRweek(date)$MMWRyear,
                      start_date = MMWRweek::MMWRweek2Date(MMWRyear=year, MMWRweek=week),
                      end_date = (start_date+6)) %>%
        dplyr::filter(!(start_date>sim_end_date)) %>%
        dplyr::filter(date==start_date) %>%
        dplyr::mutate(param = "ReduceR0") %>%
        dplyr::mutate(R_ratio = variant_effect*(1-variant_prop) + variant_effect*(1+trans_inc)*variant_prop
                      # sd_variant = variant_lb*(1-variant_prop) + variant_lb*(1+trans_inc)*variant_prop,
                      # sd_variant = (R_ratio - sd_variant)/1.96
                      ) %>%
        dplyr::mutate(variant = "B1617")


    b117_week_ <- b117_week %>%
        dplyr::filter(date < min(b1617_week$date))

    variant_data <- b1617_week %>%
        dplyr::filter(trans_inc==transmission_increase) %>%
        dplyr::bind_rows(b117_week_) %>%
        dplyr::filter(end_date >= sim_start_date) %>%
        dplyr::mutate(start_date = dplyr::if_else(start_date < sim_start_date &
                                                      end_date > sim_start_date, sim_start_date, start_date),
                      end_date = dplyr::if_else(end_date > sim_end_date, sim_end_date, end_date))

    variant_data <- variant_data %>%
        dplyr::mutate(R_ratio = round(R_ratio, 2)) %>%
        dplyr::select(week, start_date, end_date, variant, param, R_ratio) %>%
        dplyr::group_by(R_ratio) %>%
        dplyr::summarise(start_date = min(start_date),
                         end_date = max(end_date),
                         #value_sd = mean(sd_variant),
                         week = ifelse(length(week)==1, as.character(week), paste0(min(week), "-", max(week)))) %>%
        dplyr::filter(R_ratio>1)
}

#' Function to process variant data for B117/B1617
#'
#' Generate state-level variant interventions
#'
#' @param variant_path_1 path to B117 variant
#' @param variant_path_2 path to B1617 variant
#' @param sim_start_date simulation start date
#' @param sim_end_date simulation end date
#' @param projection_start_date specified to ensure interventions in the two weeks before the projection start are not aggregated
#' @param variant_lb
#' @param varian_effect change in transmission for variant default is 50% from Davies et al 2021
#' @param transmission_increase transmission increase in B1617 relative to B117
#' @param geodata
#'
#'
#' @return
#' @export
#'
#' @examples
#'
#' variant <- generate_multiple_variants(variant_path_1 = system.file("extdata", "B117-fits.csv", package = "flepiconfig"),
#'                                       variant_path_2 = system.file("extdata", "B617-fits.csv", package = "flepiconfig"))
#' variant
#'
generate_multiple_variants_state <- function(variant_path_1,
                                       variant_path_2,
                                       sim_start_date=as.Date("2020-03-31"),
                                       sim_end_date=Sys.Date()+60,
                                       projection_start_date = Sys.Date(),
                                       variant_lb = 1.4,
                                       variant_effect = 1.5,
                                       transmission_increase = 0.2,
                                       geodata
){

    if(is.null(transmission_increase)){
        transmission_increase=0.2
    }

    b117 <- readr::read_csv(variant_path_1)
    b1617 <- readr::read_csv(variant_path_2)

    sim_start_date <- as.Date(sim_start_date)
    sim_end_date <- as.Date(sim_end_date)
    projection_start_date <- as.Date(projection_start_date)

    b117_week <- b117 %>%
        dplyr::mutate(week = MMWRweek::MMWRweek(date)$MMWRweek,
               year = MMWRweek::MMWRweek(date)$MMWRyear,
               start_date = MMWRweek::MMWRweek2Date(MMWRyear=year, MMWRweek=week),
               end_date = (start_date+6)) %>%
        dplyr::rename(variant_prop = fit) %>%
        dplyr::mutate(variant = "B117") %>%
        dplyr::filter(!(start_date>sim_end)) %>%
        dplyr::filter(date==end_date) %>%
        dplyr::mutate(date=start_date) %>%
        dplyr::mutate(param = "ReduceR0") %>%
        dplyr::mutate(R_ratio = 1*(1-variant_prop) + variant_effect*variant_prop
                      # sd_variant = 1*(1-variant_prop) + variant_lb*variant_prop,
                      # sd_variant = (R_ratio - sd_variant)/1.96
        )


    # B.1.617
    b1617_week <- b1617 %>%
        dplyr::mutate(week = MMWRweek::MMWRweek(date)$MMWRweek,
                      year = MMWRweek::MMWRweek(date)$MMWRyear,
                      start_date = MMWRweek::MMWRweek2Date(MMWRyear=year, MMWRweek=week),
                      end_date = (start_date+6)) %>%
        dplyr::rename(variant_prop = fit) %>%
        dplyr::filter(!(start_date>sim_end_date)) %>%
        dplyr::filter(start_date >= as.Date("2021-04-01")) %>%
        dplyr::filter(date==end_date) %>%
        dplyr::mutate(param = "ReduceR0") %>%
        dplyr::mutate(R_ratio = 1*(1-variant_prop) + variant_effect*(1+transmission_increase)*variant_prop
                      # sd_variant = 1*(1-variant_prop) + variant_lb*(1+transmission_increase)*variant_prop,
                      # sd_variant = (R_ratio - sd_variant)/1.96
                      ) %>%
        dplyr::mutate(variant = "B1617")


    b117_week_ <- b117_week

    variant_data <- b1617_week %>%
        dplyr::bind_rows(b117_week_) %>%
        dplyr::filter(end_date >= sim_start_date) %>%
        dplyr::mutate(start_date = dplyr::if_else(start_date < sim_start_date &
                                                  end_date > sim_start_date, sim_start_date, start_date),
                      end_date = dplyr::if_else(end_date > sim_end_date, sim_end_date, end_date))

    variant_data <- variant_data %>%
        #dplyr::mutate(R_ratio = round(R_ratio, 2)) %>%
        dplyr::select(location, week, start_date, end_date, variant, param, R_ratio) %>%
        dplyr::group_by(location, week, start_date, end_date) %>%
        dplyr::summarise(R_ratio = round(prod(R_ratio)*(1/0.05))*0.05
                         #, sd_variant = sum(sd_variant)
        ) %>% # THIS IS NOT THE RIGHT SD BUT DOESN'T MATTER B/C WE DON'T USE IT
        dplyr::ungroup() %>%
        dplyr::mutate(final_week = dplyr::case_when(start_date >= lubridate::floor_date(projection_start_date-14, "week") & start_date < projection_start_date ~ 1,
                                                    start_date >= projection_start_date ~ 0,
                                                    TRUE ~ NA_real_),
                      sequential = dplyr::case_when(R_ratio == dplyr::lead(R_ratio) & R_ratio != dplyr::lag(R_ratio) ~ 1,
                                                    R_ratio == dplyr::lag(R_ratio) ~ 0,
                                                    R_ratio != dplyr::lag(R_ratio) ~ 1)) %>%
        dplyr::group_by(location) %>%
        dplyr::mutate(sequential=cumsum(sequential)) %>%
        dplyr::group_by(location, final_week) %>%
        dplyr::mutate(final_week = cumsum(final_week)) %>%
        dplyr::group_by(R_ratio, location, final_week) %>%
        dplyr::summarise(start_date = min(start_date),
                         end_date = max(end_date),
                         # value_sd = mean(sd_variant),
                         week = ifelse(length(week)==1, as.character(week), paste0(min(week), "-", max(week)))) %>%
        dplyr::select(-final_week) %>%
        dplyr::filter(R_ratio>1) %>%
        dplyr::filter(location != "US") %>%
        dplyr::rename("USPS" = "location") %>%
        dplyr::left_join(geodata %>% dplyr::select(USPS, subpop)) %>%
        dplyr::filter(!is.na(subpop)) %>%
        dplyr::ungroup()
}

#' Function to process variant data with variant compartments
#'
#' Generate state-level variant interventions
#'
#' @param variant_path_1 path to variant data with columns matching variant_compartments
#' @param sim_start_date simulation start date
#' @param sim_end_date simulation end date
#' @param projection_start_date specified to ensure interventions in the two weeks before the projection start are not aggregated
#' @param variant_lb
#' @param varian_effect change in transmission for variant default is 50% from Davies et al 2021
#' @param transmission_increase transmission increase in B1617 relative to B117
#' @param geodata
#'
#'
#' @return
#' @export
#'
#' @examples
#'
#' variant <- generate_multiple_variants(variant_path_1 = system.file("extdata", "B117-fits.csv", package = "flepiconfig"),
#'                                       variant_path_2 = system.file("extdata", "B617-fits.csv", package = "flepiconfig"))
#' variant
#'
generate_compartment_variant <- function(variant_path = "../COVID19_USA/data/variant/variant_props_long.csv",
                                         variant_compartments = c("WILD", "ALPHA", "DELTA"),
                                         transmission_increase = c(1, 1.45, (1.6*1.6)),
                                         geodata,
                                         sim_start_date = as.Date("2020-03-31"),
                                         sim_end_date = Sys.Date()+60){
    trans_incr <- dplyr::tibble(variant_compartments,
                                transmission_increase)

    variant_data <- readr::read_csv(variant_path)

    if(!("source" %in% colnames(variant_data))){
        variant_data$source <- ""
    }
    variant_data <- variant_data %>% dplyr::full_join(trans_incr) %>%
        dplyr::rename(date = Update, USPS = source) %>%
        dplyr::mutate(trans_mult = (trans_incr * prop)) %>%
        dplyr::group_by(date, USPS) %>%
        dplyr::summarise(trans_mult = sum(trans_mult))

    sim_start_date <- as.Date(sim_start_date)
    sim_end_date <- as.Date(sim_end_date)

    variant_data <- variant_data %>%
        dplyr::mutate(week = MMWRweek::MMWRweek(date)$MMWRweek,
                      year = MMWRweek::MMWRweek(date)$MMWRyear,
                      start_date = MMWRweek::MMWRweek2Date(MMWRyear=year, MMWRweek=week),
                      end_date = (start_date+6)) %>%
        dplyr::filter(!(start_date>sim_end_date)) %>%
        dplyr::filter(date==end_date) %>%
        dplyr::mutate(date=start_date) %>%
        dplyr::mutate(param = "ReduceR0") %>%
        dplyr::rename(R_ratio = trans_mult) %>%
        dplyr::mutate(sd_variant = (sqrt(R_ratio)-1)/5)

    variant_data <- variant_data %>%
        dplyr::filter(end_date >= sim_start_date) %>%
        dplyr::mutate(start_date = dplyr::if_else(start_date < sim_start_date &
                                                      end_date > sim_start_date, sim_start_date, start_date),
                      end_date = dplyr::if_else(end_date > sim_end_date, sim_end_date, end_date))

    variant_data <- variant_data %>%
        dplyr::mutate(R_ratio = round(R_ratio, 2)) %>%
        dplyr::select(USPS, week, start_date, end_date, param, R_ratio, sd_variant) %>%
        dplyr::mutate(R_ratio = round(R_ratio*(1/0.05))*0.05, sd_variant = mean(sd_variant)) # THIS IS NOT THE RIGHT SD BUT DOESN'T MATTER B/C WE DON'T USE IT

    # Combine interventions
    dates_start_ <- sort(unique(variant_data$start_date))
    for (d in 1:length(dates_start_)){
        variant_data <- variant_data %>%
            dplyr::mutate(date_curr = (start_date==dates_start_[d] | end_date==(dates_start_[d]-1)),
                          date_comb = ifelse(date_curr==TRUE, "comb_group", as.character(start_date))) %>%
            dplyr::group_by(USPS, param, R_ratio, date_comb) %>%
            dplyr::summarise(start_date=min(start_date), end_date=max(end_date),
                             sd_variant = round(mean(sd_variant,na.rm=TRUE),4))
    }
    variant_data <- variant_data %>% dplyr::as_tibble() %>% dplyr::select(-date_comb) %>% dplyr::distinct()
    variant_data <- variant_data %>%
        dplyr::filter(R_ratio>1) %>%
        dplyr::filter(USPS != "US") %>%
        dplyr::left_join(geodata %>% dplyr::select(USPS, subpop))

    return(variant_data)
}

