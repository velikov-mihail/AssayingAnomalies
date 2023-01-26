function makeIndustryClassifications(Params)
% PURPOSE: This function creates vand stores various industry
% classifications. Those include 4-digit SIC code, FF10, FF17, and FF49
%------------------------------------------------------------------------------------------
% USAGE:   
% makeIndustryClassifications(Params)              
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
% makeIndustryClassifications(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeFF10Indus(), makeFF17Indus(), makeFF49Indus()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('Now working on industry classifications at %s.\n', char(datetime('now')));

% Store the Data directory path
dataPath=[Params.directory,'Data/'];

% Load the SIC code variable
load siccd

% Make the industry classifications
SIC = siccd;
[FF10, FF10Names] = makeFF10Indus(SIC); 
[FF17, FF17Names] = makeFF17Indus(SIC); 
[FF49, FF49Names] = makeFF49Indus(SIC); 

% Store the industry classification matrices
save([dataPath,'SIC.mat'],  'SIC');
save([dataPath,'FF10.mat'], 'FF10', 'FF10Names');
save([dataPath,'FF17.mat'], 'FF17', 'FF17Names');
save([dataPath,'FF49.mat'], 'FF49', 'FF49Names');
