# AssayingAnomalies
 
CONTENTS OF THIS FILE
---------------------

 * Introduction
 * Requirements
 * Inputs
 * Setup
 * Usage
 * Acknowledgements
 * References


INTRODUCTION
------------

Note: Please cite <a href = "https://papers.ssrn.com/abstract=4338007" target="_blank">Novy-Marx and Velikov (2023)</a> when using this repository.

Authors: Mihail Velikov <velikov@psu.edu> & Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>. 

This repository contains a beta version of the MATLAB Toolkit that accompanies Novy-Marx and Velikov (2023) and is to be used for empirical academic asset pricing research, particularly focused on studying anomalies in the cross-section of stock returns. After setting up several parameters, the first main script in the Toolkit (setup_library.m) automatically downloads through a JDBC connection with WRDS and stores on the hard drive return data from CRSP and accounting data from COMPUSTAT. 

Following the initial set-up, the MATLAB Toolkit contains a script (use_library.m) that demonstrates to users how to conduct standard tests in empirical asset pricing research such as univariate and double portfolio sorts and Fama-MacBeth cross-sectional regressions in only a few lines.

The MATLAB Toolkit also contains a script (test_signal.m) that after the initial setup can fully replicate the results in Novy-Marx and Velikov (2023). This script can also be used to perform all recommended tests in the protocol for testing new anomalies proposed in Novy-Marx and Velikov (2023) by just changing the test signal input.

For more information and step-by-step tutorials on how to run the setup and use the library see the companion website and web application at <a href = "http://assayinganomalies.com" target="_blank">http://assayinganomalies.com</a>.

REQUIREMENTS
------------

Full usage of the library requires:
* WRDS subscription with access to
    * Monthly and daily CRSP
    * Annual and quarterly COMPUSTAT
    * CRSP/COMPUSTAT merged tool from WRDS. 
* MATLAB 2021a or more recent version with database toolbox 
* JAVA Heap Memory adjusted to max available (48 GB recommended) 
    * Home -> Preferences -> General -> Java Heap Memory
* The daily return data and the anomaly zoo tests currently require significant RAM, especially if going back to 1925 (64GB or more recommended)
* The optional combination trading costs measure that includes the high-frequency spreads from Chen and Velikov (2021) requires the following WRDS subscriptions:
    * WRDS cloud
    * ISSM
    * Daily TAQ
    * Monthly TAQ
    * WRDS TAQ IID
* Printing the output from the Novy-Marx and Velikov (2023) protocol requires Ghostscript interpreter installation 


INPUTS
------------

The code asks the user to select the unzipped library directory as well as to input the user's WRDS username and password. The following parameters also need to be specified in setup_library.m:

* SAMPLE_START - sample start date, default is 1925 (recommended to start in 1962 if short on memory)
* SAMPLE_END - sample end date, default is 2021
* domComEqFlag- a flag (0 or 1 by default) that indicates whether to limit the library to domestic common equity (share codes 10 or 11)
* COMPVarNames- file with names of COMPUSTAT annual & quarterly variables to download (default included with code - COMPUSTAT Variable Names.csv) or 'All' to download all variables (not recommended as there are ~1,000 variables)
* tcostsType- parameters specifying the choice of transaction costs 
     * 'gibbs' - Gibbs effective spread measure from Hasbrouck (2009) 
     * 'lf_combo' (default) - low-frequency combination measure from Chen and Velikov (2021) 
     * 'full' - full combination measure from Chen and Velikov (2021)

Additional inputs a user needs to set up the library:
* Gibbs file (crspgibbs.csv) - input for the Gibbs effective spread measure used for transaction costs; file with Gibbs spreads up to 2021 and Hasbrouck's (2009) SAS code included with the Toolkit ( See 3) in SETUP below)
* Optional high-frequency (TAQ & ISSM) effective spreads file (See 4) in SETUP below)


SETUP
-----

You can find a code overview and step-by-step tutorials at our companion website [http://assayinganomalies.com](http://assayinganomalies.com).

Recommended order of operations:
1) Download the code from this repository 
2) Set the Java Heap Memory in your MATLAB settings to 48GB or the maximum available.
    * Home -> Preferences -> General -> Java Heap Memory
3) (Optionally) run the Gibbs code either locally (need to download through ftp crsp.dsf & crsp.dse) or on WRDS cloud. Store the file (crspgibbs.csv) in the working directory to use as an input when creating the trading costs measure. 
     * Input file containing Gibbs effective spreads through 2021 is included in the repository. 
4) (Optionally) download the code and follow the instructions for calculating the high-frequency effective spreads from TAQ and ISSM from https://github.com/chenandrewy/hf-spreads-all
     * This step is required to use the combination transaction costs measure from Chen and Velikov (2021)
     * After running the code on the WRDS cloud, you should download the output file, hf_monthly.csv, and store it in the working directory
5) Enter the parameters at the beginning of setup_library.m script.
6) Run setup_library.m (<a href = "https://sites.psu.edu/assayinganomalies/code/setup/" target="_blank">step-by-step tutorial</a>)

USAGE
-----

7) use_library.m 
    * Explore the functionality of the Toolkit  (<a href = "https://sites.psu.edu/assayinganomalies/code/usage/" target="_blank">step-by-step tutorial</a>)
8) test_signal.m - the default setting replicates the results in Novy-Marx and Velikov (2023) using the monetary policy exposure (MPE) index from Ozdagli and Velikov (2020).
    * Run the "Assaying Anomalies" protocol from Novy-Marx and Velikov (2023)
    * Default setting replicates the results in Novy-Marx and Velikov (2023) using the monetary policy exposure (MPE) index from Ozdagli and Velikov (2020).
    * To test a new signal, adjust the signalInfo structure in lines 26-32 of the script
    * Printing the output requires Ghoscript interpreter to be installed


ACKNOWLEDGEMENTS
----------------
We thank Andrea Frazzini for sharing scripts that inspired the organization of some of our code. For helpful comments and for testing earlier versions we would like to thank Don Bowen, Andrew Detzel, Ulas Misirli, Rob Parham, Haowei Yuan, and PhD students at Penn State University and the University of Rochester. 


REFERENCES
-----

Chen, A. and M. Velikov, 2021, Zeroing in on the expected returns of anomalies, Journal of Financial and Quantitative Analysis, Forthcoming<br />
Hasbrouck, J., 2009, Trading costs and returns for U.S. equities: Estimating effective costs from daily data, Journal of Finance, 64, 1445 - 1477<br />
Novy-Marx, R. and M. Velikov, 2023, Assaying Anomalies, Working paper<br />
Ozdagli, A. and M. Velikov, 2020, Show Me the Money: The Monetary Policy Risk Premium, Journal of Financial Economics, 143 (1), 80-106
