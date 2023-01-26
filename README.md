# AssayingAnomalies
 
CONTENTS OF THIS FILE
---------------------

 * Introduction
 * Requirements
 * Inputs
 * Setup
 * Usage



INTRODUCTION
------------

Note: Please cite Novy-Marx and Velikov (2023) when using this repository.

Authors: Mihail Velikov <velikov@psu.edu> & Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>. 

This repository contains a prelminary (still under development) version of the library of MATLAB code (the "MATLAB AP library" or just "library") that accompanies Novy-Marx and Velikov (2023) and is to be used for empirical academic asset pricing research, particularly focused on studying anomalies in the cross-section of stock returns. After setting up several parameters, the first main script in the library (setup_library.m) automatically downloads through a JDBC connection with WRDS and stores on the hard drive return data from CRSP and accounting data from COMPUSTAT. 

Following the initial set-up, the MATLAB AP library contains a script (use_library.m) that demonstrates to users how to conduct standard tests in empirical asset pricing research such as univariate and double portfolio sorts and Fama-MacBeth cross-sectional regressions. The library is still in development and in the near future it will contain a separate script containing replications of many classic papers in empirical asset pricing. 

The MATLAB AP library also contains a script (test_signal.m) that fully replicates the results in Novy-Marx and Velikov (2023). By just changing the test signal input (either by reading it from a (permno, month, signal) .csv or constructing the signal in the script), this script can also be used to perform all recommended tests in the protocol for testing new anomalies proposed in Novy-Marx and Velikov (2023). 


REQUIREMENTS
------------

Full usage of the library requires the following:
* WRDS subscription with access to the following:
    * Monthly and daily CRSP
    * Annual and quarterly COMPUSTAT
    * CRSP/COMPUSTAT merged tool from WRDS. 
* MATLAB 20YYx with database toolbox 
* JAVA Heap Memory adjusted to max available (48 GB recommended) 
    * Home -> Preferences -> General -> Java Heap Memory
* The daily return data and the anomaly zoo tests currently require significant RAM (64GB or more recommended)
* The optional combination trading costs measure that includes the high-frequency spreads from Chen and Velikov (2021) requires the following WRDS subscriptions:
    * WRDS cloud
    * ISSM
    * Daily TAQ
    * Monthly TAQ
    * WRDS TAQ IID


INPUTS
------------

The code asks the user to select the unzipped library directory as well as to input the user's WRDS username and password. The following parameters also need to be specified in setup_library.m:

* domesticCommonEquityShareFlag - a flag (0 or 1 by default) that indicates whether to limit the library to domestic common equity (share codes 10 or 11)
* SAMPLE_START - sample start date, default is 1925 (recommended to start in 1962 if short on memory)
* SAMPLE_END - sample end date, default is 2020
* COMPUSTATVariablesFileName - file with names of COMPUSTAT annual & quarterly variables to download (default included with code - COMPUSTAT Variable Names.csv) or 'All' to download all variables (not recommended as there are ~1,000 variables)
* tcosts - parameters specifying the choice of transaction costs 
     * 'gibbs' - Gibbs effective spread measure from Hasbrouck (2009) 
     * 'lf_combo' (default) - low-frequency combination measure from Chen and Velikov (2021) 
     * 'full' - full combination measure from Chen and Velikov (2021)

Additional inputs a user need to set up the library:
* Gibbs file (crspgibbsYYYY.csv, where YYYY=SAMPLE_END+1) - input for the Gibbs effective spread measure used for transaction costs, 2021 file and Hasbrouck's (2009) SAS code included 
* Optional high-frequency (TAQ & ISSM) effective spreads file (See 3) in SETUP below)

SETUP
-----

Order of operations:
1) Download the code from this repository 
2) Set the Java Heap Memory in your MATLAB settings to 48GB or the maximum available.
    * Home -> Preferences -> General -> Java Heap Memory
3) (Optionally) run the Gibbs code either locally (need to download through ftp crsp.dsf & crsp.dse) or on WRDS cloud. Store the file (crspgibbsYYYY.csv) in the working directory to use as an input when creating the trading costs measure. 
     * Input file containing Gibbs effective spreads through 2020 is included in the repository. 
4) (Optionally) download the code and follow the instructions for calculating the high-frequency effective spreads from TAQ and ISSM from https://github.com/chenandrewy/hf-spreads-all
     * This step is required to use the combination transaction costs measure from Chen and Velikov (2021)
     * After running the code on the WRDS cloud, you should download the output file, hf_monthly.csv
5) Enter the parameters at the beginning of setup_library.m script.
6) Run setup_library.m


USAGE
-----

Order of operations (description to be updated):
1) use_library.m
2) test_signal.m

REFERENCES
-----

Chen, A. and M. Velikov, 2021, Zeroing in on the expected returns of anomalies, JFQA, Forthcoming<br />
Hasbrouck, J., 2009, Trading costs and returns for U.S. equities: Estimating effective costs from daily data, The Journal of Finance, 64, 1445 - 1477<br />
Novy-Marx, R. and M. Velikov, 2023, Assaying Anomalies, Working paper
