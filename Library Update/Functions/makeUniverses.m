function makeUniverses(Params)
% PURPOSE: This function creates and stores a structure that contains
% indicators for small/large caps based on two classifications: Fama-French
% (< or > than NYSE 50th percentile) and Russell ((not) in the top 1000
% stocks based on market cap)
%------------------------------------------------------------------------------------------
% USAGE:   
% makeUniverses(Params)
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
% makeUniverses(Params)             
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses rowrank(), runUnivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


% Create the data path
dataPath = [Params.directory,'Data/'];

% Make the Fama-French and Russell universes
load ret
load me
load dates
load NYSE
load ff

rme = rowrank(me,0,1);

universe(1).head = {'ff'};
universe(1).ind = makeUnivSortInd(me,2,NYSE);
universe(1).res = runUnivSort(ret,universe(1).ind,dates,me,'factorModel',1,'printResults',0,'plotFigure',0);
universe(1).xret = universe(1).res.pret(:,1:2) - [rf rf];

universe(2).head = {'Russell'};
temp = (rme > 1000 & rme <= 3000)*1 + (rme <= 1000)*2; temp(temp == 0) = nan;
universe(2).ind = temp;
universe(2).res = runUnivSort(ret,universe(2).ind,dates,me,'factorModel',1,'printResults',0,'plotFigure',0);
universe(2).xret = universe(2).res.pret(:,1:2) - [rf rf];

save([dataPath,'universe.mat'], 'universe');

% Make cumulative market cap percentile
tempme = me + (rand(size(me)) - 0.5)/1000000;
rme = rowrank(-tempme);

mep = nan(size(me));

for i = 1:rows(me)
    temp = me(i,:); 
    ii = isfinite(temp);
    temp(isnan(temp)) = [];
    temp = cumsum(-sort(-temp)); temp = temp/temp(end);
    jj = rme(i,ii);
    mep(i,ii) = temp(jj);
end

save([dataPath,'mep.mat'], 'mep');

fprintf('Universe creation complete.\n');


