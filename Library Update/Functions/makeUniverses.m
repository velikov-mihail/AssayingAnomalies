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
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Create the data path
dataPath = [Params.directory,'Data/'];

% Make the Fama-French and Russell universes
load ret
load me
load dates
load NYSE
load ff

% Store the ranks based on market cap in descending order. E.g., in
% December 2020 Apple (permno = 14593) has rank 1.
rme = tiedrank(-me')';

% Do the FF universe first.
universe(1).head = {'ff'};
indFF = makeUnivSortInd(me, 2, NYSE);
universe(1).ind = indFF;
universe(1).res = runUnivSort(ret, indFF, dates, me, 'factorModel', 1, ...
                                                               'printResults', 0, ...
                                                               'plotFigure', 0);
universe(1).xret = universe(1).res.pret(:,1:2) - [rf rf];

% And the Russell universe next
universe(2).head = {'Russell'};
indRuss = 1 * (rme > 1000 & rme <= 3000) + ...
          2 * (rme <= 1000); 
indRuss(indRuss == 0) = nan;
universe(2).ind = indRuss;
universe(2).res = runUnivSort(ret, indRuss, dates, me, 'factorModel', 1, ...
                                                       'printResults', 0, ...
                                                       'plotFigure', 0);
universe(2).xret = universe(2).res.pret(:,1:2) - [rf rf];

% Store the universes
save([dataPath,'universe.mat'], 'universe');

% Make cumulative market cap percentile. Add a tiny bit of noise to ensure
% proper bucketing
tempme = me + (rand(size(me)) - 0.5)/1000000;
rme = tiedrank(-tempme')';

% Initialize the cumulative market cap percentile matrix
mep = nan(size(me));

% Store number of months
nMonts = size(me, 1);

% loop over the months
for i = 1:nMonts
    temp = me(i,:); 
    ii = isfinite(temp);
    temp(isnan(temp)) = [];
    temp = cumsum(-sort(-temp)); 
    temp = temp/temp(end);
    jj = rme(i,ii);
    mep(i,ii) = temp(jj);
end

% Store the mep matrix
save([dataPath,'mep.mat'], 'mep');

fprintf('Universe creation complete.\n');


