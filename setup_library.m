clear
clc

% Initialize some variables
Params.directory = [strrep(uigetdir([],'Select folder where setup_library.m is located:'),'\','/'),'/']; % Select the package directory
Params.username=input('Enter your WRDS username: ','s'); % Input your WRDS username
Params.pass=input('Enter your WRDS password: ','s'); % Input your WRDS password
Params.domesticCommonEquityShareFlag=1; % Leave only domestic common equity (share code 10 or 11)
Params.SAMPLE_START=1925;
Params.SAMPLE_END=2020;
Params.COMPUSTATVariablesFileName='COMPUSTAT Variable Names.csv'; % Either name of file or 'All' to download all ~1000 COMPUSTAT variables.
Params.driverLocation=[Params.directory,'Library Update/Inputs/WRDS PostgreSQL JDBC Driver/postgresql-42.2.9.jar'];
Params.tcosts='full'; % Choose tcosts type: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs

% Set up the directory
restoredefaultpath; % Start with the default path
addpath(genpath(Params.directory)); % Add the directory with the MATLAB asset pricing package
cd(Params.directory); % Make it the current folder
warning('off','all')

% Start a log file
startLogFile(Params);

% Set up the WRDS PostgreSQL JDBC connection
setupWRDSConn(Params);

% Download & store all the CRSP data we'll need 
getCRSPData(Params);

% Make CRSP data
makeCRSPMonthlyData(Params);

% Make additional CRSP variables
makeCRSPDerivedVariables(Params);

% Download & store all the COMPUSTAT data we'll need (both annual and quarterly)
getCOMPUSTATData(Params);

% Merge CRSP & COMPUSTAT, store all variables
mergeCRSPCOMP(Params);

% Make additional COMPUSTAT variables
makeCOMPUSTATDerivedVariables(Params);

% Download & store all the daily CRSP data we'll need 
getCRSPDailyData(Params);

% Construct the raw variables from the CRSP daily data
makeCRSPDailyData(Params);

% Make additional variables that use CRSP daily
makeCRSPDailyDerivedVariables(Params);

% Make transaction costs
makeTCosts(Params)

% Make anomalies
makeNovyMarxVelikovAnomalies(Params)

% Make betas
makeBetas(Params);

% End the log file
diary off

%% Notes & to-do
 
% If you need additional COMPUSTAT variables, run the following in the main
% library folder:
% getCOMPUSTATAdditionalData(Params.username,Params.pass,'ACT','annual');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,'ACT, AT','annual');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,'ACTQ','quarterly');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,'ACTQ, ATQ','quarterly');


