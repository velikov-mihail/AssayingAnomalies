function makeIndustryReturns(Params)
% PURPOSE: This function creates and stores the value-weighted returns for
% the FF49 industries
%------------------------------------------------------------------------------------------
% USAGE:   
% makeIndustryReturns(Params)             
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
% makeIndustryReturns(Params)             
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires makeIndustryClassifications() to have been run.
%       Uses runUnivSort(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

dataPath = [Params.directory,'Data/'];

load ret
load me
load FF49
load dates

res = runUnivSort(ret,FF49,dates,me,'factorModel',1,'printResults',0,'plotFigure',0,'addLongShort',0); 

% Make and store the industry portfolio returns
iret = res.pret(:,1:49);
save([dataPath,'iret.mat'], 'iret');

% Assign the industry portfolio returns to individual stocks & store 
ireta = nan(size(ret));
for i = 1:49
    temp = repmat(iret(:,i),1,size(ret,2));
    ireta(FF49==i) = temp(FF49==i);
end

save([dataPath,'ireta.mat'], 'ireta');

fprintf('Industry returns calculation complete.\n');
