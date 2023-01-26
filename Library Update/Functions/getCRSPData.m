function getCRSPData(Params)
% PURPOSE: This function downloads and stores the required tables from the CRSP monthly file
%------------------------------------------------------------------------------------------
% USAGE:   
% getCRSPData(Params)              % Downloads and stores the required tables from the CRSP monthly file                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% getCRSPData(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses callWRDSConnection, getWRDSTable
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


% Timekeeping
fprintf('\n\n\nNow working on downloading the raw CRSP. Run started at %s.\n',char(datetime('now')));

% Check if the Data & Data\CRSP subdirectories exist. If not, make them
if ~exist([Params.directory,'Data'], 'dir')
  mkdir([Params.directory,'Data']);
end
if ~exist([Params.directory,'Data/CRSP'], 'dir')
    mkdir([Params.directory,'Data/CRSP'])
end
addpath(genpath(Params.directory));


crspDirPath=[Params.directory,'Data/CRSP/'];

% Call the WRDS connection
WRDS=callWRDSConnection(Params.username,Params.pass);

% Download and save the CRSP header CRSP.MSFHDR table
getWRDSTable(WRDS,'CRSP','MSFHDR',crspDirPath);

% Download and save the CRSP monthly stock file CRSP.MSF table
getWRDSTable(WRDS,'CRSP','MSF',crspDirPath);

% Download and save the CRSP delisting returns CRSP.MSEDELIST table
getWRDSTable(WRDS,'CRSP','MSEDELIST',crspDirPath);

% Download and save the CRSP monthly stock file with share code information
getWRDSTable(WRDS,'CRSP','MSEEXCHDATES',crspDirPath);

% Download and save the CRSP CCM Linkhist table
getWRDSTable(WRDS,'CRSP','CCMXPF_LNKHIST',crspDirPath);

% Download and save the CRSP CCM Linkhist table
getWRDSTable(WRDS,'CRSP','STOCKNAMES',crspDirPath);

close(WRDS);

fprintf('CRSP raw data download ended at %s.\n',char(datetime('now')));








