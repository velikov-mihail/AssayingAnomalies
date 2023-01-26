clear
clc

% Set up the path to include the directory with the MATLAB package
directoryPrompt  = 'Select folder where setup_library.m is located:';
Params.directory = [strrep(uigetdir([], directoryPrompt),'\','/'),'/']; 
restoredefaultpath;                                                        
addpath(genpath(Params.directory));                                        
cd(Params.directory);                                                      
warning('off','all')

% Initialize several variables
Params.username     = usernameUI();                                        % Input your WRDS username
Params.pass         = passwordUI();                                        % Input your WRDS password
Params.SAMPLE_START = 1925;                                                % Sample start year
Params.SAMPLE_END   = 2021;                                                % Sample end year
Params.domComEqFlag = 1;                                                   % Flag for domestic common equity (1 => use only share code 10 or 11)
Params.COMPVarNames = 'COMPUSTAT Variable Names.csv';                      % Either name of file with COMPUSTAT variable names or 'All' to download all ~1000 variables.
Params.tcostsType   = 'lf_combo';                                          % Tcosts type: 'gibbs'    - just gibbs
                                                                           %              'lf_combo' - low-freq 4-measures combo; 
                                                                           %              'full'     - low-freq 4-measures combo + TAQ + ISSM; 

% Check Java Heap Memory
checkJavaHeapMemory();

% Start a log file
startLogFile(Params.directory, 'library_setup');

% Set up the WRDS PostgreSQL JDBC connection
setupWRDSConn(Params);

% Download & store all the CRSP data we'll need 
getCRSPData(Params);

% Make CRSP data
makeCRSPMonthlyData(Params);

% Make additional CRSP variables
makeCRSPDerivedVariables(Params);

% Download & store all the COMPUSTAT data we'll need (annual and quarterly)
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
makeTradingCosts(Params)

% Make anomalies
makeNovyMarxVelikovAnomalies(Params)

% Make betas
makeBetas(Params);

% End the log file
diary off

%% Notes & to-do
 
% If you need additional COMPUSTAT variables (e.g., these random ones), run the following:
% getCOMPUSTATAdditionalData(Params.username, Params.pass, {'RDIP'}, 'annual');
% getCOMPUSTATAdditionalData(Params.username, Params.pass, {'RDIP', 'RCP'}, 'annual');
% getCOMPUSTATAdditionalData(Params.username, Params.pass, {'RDIPQ'}, 'quarterly');
% getCOMPUSTATAdditionalData(Params.username, Params.pass, {'RDIPQ', 'RCPQ'}, 'quarterly');


