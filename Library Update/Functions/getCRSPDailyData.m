function getCRSPDailyData(Params)
% PURPOSE: This function downloads and stores the required tables from the CRSP daily file
%------------------------------------------------------------------------------------------
% USAGE:   
% getCRSPDailyData(Params)              % Downloads and stores the required tables from the CRSP daily file                                 
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
% getCRSPDailyData(Params)              
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
fprintf('\n\n\nNow working on downloading the raw daily CRSP. Run started at %s.\n',char(datetime('now')));

% Check if the Data/CRSP/daily subdirectory exists. If not, make it
if ~exist([Params.directory,'Data/CRSP/daily'], 'dir')
    mkdir([Params.directory,'Data/CRSP/daily'])
end
addpath(genpath(Params.directory));

% Call the WRDS connection
WRDS=callWRDSConnection(Params.username,Params.pass);

yearCutoffs=[1925 1950 1975 1985:5:Params.SAMPLE_END];
yearCutoffs(yearCutoffs<=Params.SAMPLE_START)=[];
if yearCutoffs(1)>(Params.SAMPLE_START-1)
    yearCutoffs=[Params.SAMPLE_START-1 yearCutoffs];
end
yearCutoffs(yearCutoffs>Params.SAMPLE_END)=[];
if yearCutoffs(end)<Params.SAMPLE_END
    yearCutoffs=[yearCutoffs Params.SAMPLE_END];
end

for i=2:length(yearCutoffs)
    % Download and save the CRSP daily stock file CRSP.DSF`i' table
    fprintf('Now working on %d-%d daily stock file.\n',yearCutoffs(i-1),yearCutoffs(i));
    customQuery=['select permno, date, cfacpr, cfacshr, bidlo, askhi, prc, vol, ret, bid, ask, shrout, openprc, numtrd from CRSP.DSF where date>''',char(num2str(yearCutoffs(i-1))),'1231'' and date<=''',char(num2str(yearCutoffs(i))),'1231'''];
    getWRDSTable(WRDS,'CRSP',['DSF',char(num2str(i-1))],'Data/CRSP/daily/','customQuery',customQuery);
end

% Download and save the CRSP delisting returns CRSP.DSEDELIST table
getWRDSTable(WRDS,'CRSP','DSEDELIST','Data/CRSP/daily/');

close(WRDS);

fprintf('Daily CRSP raw data download ended at %s.\n',char(datetime('now')));








