function makeCRSPDerivedVariables(Params)
% PURPOSE: This function creates variables that are directly derived from the
% matrices created from the CRSP monthly file
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCRSPDerivedVariables(Params)              % Creates additional variables from the CRSP monthly matrices
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
% makeCRSPDerivedVariables(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires makeCRSPMonthlyData() to have been run.
%       Uses makeIndustryClassifications(), getFFFactors(),
%       makeIndustryReturns(), makeUniverses(), mpp(), testCRSPData()
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

fprintf('\n\n\nNow working on making variables from CRSP. Run started at %s.\n',char(datetime('now')));

dataPath = [Params.directory,'Data/'];
crspDirPath = [Params.directory,'Data/CRSP/'];

% Adjust the returns for delisting
load ret_x_dl
load permno
load dates
% Read the CRSP delist returns file
opts = detectImportOptions([crspDirPath,'crsp_msedelist.csv']);
crsp_msedelist = readtable([crspDirPath,'crsp_msedelist.csv'],opts);
crsp_msedelist(~ismember(crsp_msedelist.permno,permno) | crsp_msedelist.dlstdt==datetime(Params.SAMPLE_END,12,31),:) = [];

ret = ret_x_dl;
for i = 1:height(crsp_msedelist)       
    c = find(permno==crsp_msedelist.permno(i));
    r = find(isfinite(ret(:,c)),1,'last')+1;
    ret(r,c) = crsp_msedelist.dlret(i);        
end
save([dataPath,'ret.mat'],'ret');
c = find(permno==11754);
r = find(dates==201201);
fprintf('Adjusting for delisting complete. Kodak''s delisting return was %2.4f in %d\n',ret(r,c),dates(r));
clear c r  dates dd dlret i index MM permno ret ret_x_dl retdl1 tt

% Make market capitalization
load prc
load shrout
me = abs(prc).*shrout/1000;
me(me == 0) = nan;
save([dataPath,'me.mat'],'me');
clear prc shrout me

% Make dates for plotting
load dates
pdates = floor(dates/100) + mod(dates,100)/12;
save([dataPath,'pdates.mat'],'pdates');
clear dates pdates

% Make the NYSE indicator variable
load exchcd
NYSE = (exchcd == 1)*1;
save([dataPath,'NYSE.mat'],'NYSE');
clear exchcd NYSE

% Rename the SIC code variable and create Fama/French industry variables 
makeIndustryClassifications(Params);

% Download, clean up, and save the Fama-French Factors from Ken French's website
getFFFactors(Params);

% Make & save the industry returns, based on FF49 classification
makeIndustryReturns(Params);

% Make different universes
makeUniverses(Params);

% Make Share Issuance Variables
load shrout
load cfacshr
ashrout = shrout.*cfacshr;
dashrout = log(ashrout./lag(ashrout,12,nan)); % percent change in split adjusted shares outstanding
save([dataPath,'ashrout.mat'],'ashrout');
save([dataPath,'dashrout.mat'],'dashrout');

% Make Momentum variables
load ret
R = makePastPerformance(ret,12,1); % "R" = gross returns (past perfromance)-- cumulates returns (gross) from 12 month ago to one month ago (NOT including last month)
R3613 = makePastPerformance(ret,36,12); % Cumulates gross returns from 36 month ago to 12 months ago (for DeBont and Thaler long run reversals)
R127 = makePastPerformance(ret,12,6); % Cumulates gross returns from 12 month ago to 6 months ago ("intermediate horizon past perfromance")
R62 = makePastPerformance(ret,6,1); % Cumulates gross returns from 6 month ago to 1 month ago ("recent horizon past perfromance")

save([dataPath,'R.mat'],'R'); % worth saving, as it takes awhile to run
save([dataPath,'R3613.mat'],'R3613');
save([dataPath,'R127.mat'],'R127');
save([dataPath,'R62.mat'],'R62');

% Test that your data matches up with some reference data 
testCRSPData(Params);

fprintf('CRSP monthly variables run ended at %s.\n', char(datetime('now')));
