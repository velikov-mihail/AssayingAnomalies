function getCOMPUSTATData(Params)
% PURPOSE: This function downloads and stores the required tables from the CRSP monthly file
%------------------------------------------------------------------------------------------
% USAGE:   
% getCOMPUSTATData(Params)             % Downloads and stores the required
%                                        tables from the COMPUSTAT annual & quarterly files
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
% getCOMPUSTATData(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses callWRDSConnection(), getCOMPUSTATQuery(), getWRDSTable()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Timekeeping
fprintf('\n\n\nNow working on downloading the raw COMPUSTAT. Run started at %s.\n',char(datetime('now')));

% Check if the Data\COMPUSTAT subdirectory exist. If not, make them
compustatDirPath = [Params.directory,'Data/COMPUSTAT/'];
if ~exist(compustatDirPath, 'dir')
    mkdir(compustatDirPath)
end
addpath(genpath(Params.directory));

% Call the WRDS connection
WRDS = callWRDSConnection(Params.username,Params.pass);

% Get the annual COMPUSTAT data. 
% First, we need to get a string with the query we want to run on the WRDS
% server for the COMPUSTAT data. The query selects all variables we have in
% the Excel file. 
COMPUSTATAnnualQuery = getCOMPUSTATQuery(WRDS, Params, 'annual');
getWRDSTable(WRDS, 'COMP', 'FUNDA', 'dirPath', compustatDirPath, ...
                                    'customQuery', COMPUSTATAnnualQuery);

% Get the quarterly COMPUSTAT data. Same as the annual data above.
COMPUSTATQuarterlyQuery = getCOMPUSTATQuery(WRDS, Params, 'quarterly');
getWRDSTable(WRDS, 'COMP', 'FUNDQ', 'dirPath', compustatDirPath, ...
                                    'customQuery', COMPUSTATQuarterlyQuery);

% Close the WRDS connection
close(WRDS);

% Timekeeping
fprintf('COMPUSTAT raw data download ended at %s.\n',char(datetime('now')));

