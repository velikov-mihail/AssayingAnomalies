function [resBasicSorts, resCondSorts] = makeBasicSortsResults(testSignal,timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023).  It creates the basic sorts results for Tables 1, 2, and 3.
%------------------------------------------------------------------------------------------
% USAGE: 
%       resBasicSorts = makeBasicSortsResults(newSignal,timePeriod);                   
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -newSignal - matrix with the variable used for sorting        
%       -timePeriod - time period
%------------------------------------------------------------------------------------------
% Output:
%       -resBasicSorts - vector (nAnoms x 1) of structures with univariate
%       sort results
%       -resCondSorts - vector (nAnoms x 1) 
%------------------------------------------------------------------------------------------
% Examples: 
%       resBasicSorts = makeBasicSortsResults(newSignal,timePeriod);                      
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeUnivSortInd(), runUnivSort(), calcGenAlpha().
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.


fprintf('\nNow working on getting the basic sort results. Run started at %s.\n\n',char(datetime('now')));

% Load all the data we'll need
load ret
load dates
load NYSE
load me
load tcosts
load ff
load ff_tc

s = find(dates == timePeriod(1));
e = find(dates == timePeriod(2));

% Start with the univariate sorts
% Loop over the factor models
count = 1;

for f = [1 3 4 5 6] 
    
    % NYSE breaks
    ind = makeUnivSortInd(testSignal, 5, NYSE);
    
    % Value-weighted sort
    resBasicSorts(1, count).res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                                                   'weighting', 'v', ...
                                                                   'factorModel', f, ...
                                                                   'printResults', 0, ...
                                                                   'plotFigure',0);
    
    % Equal-weighted sort
    resBasicSorts(2, count).res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                                                   'weighting', 'e', ...
                                                                   'factorModel', f, ...
                                                                   'printResults', 0, ...
                                                                   'plotFigure',0);
    
    % Name breaks
    ind = makeUnivSortInd(testSignal, 5);    
    resBasicSorts(3, count).res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                                                   'weighting', 'v', ...
                                                                   'factorModel', f, ...
                                                                   'printResults', 0, ...
                                                                   'plotFigure',0);
    % Cap breaks
    ind = makeUnivSortInd(testSignal, 5, 'portfolioMassInd', me);
    resBasicSorts(4, count).res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                                                   'weighting', 'v', ...
                                                                   'factorModel', f, ...
                                                                   'printResults', 0, ...
                                                                   'plotFigure',0);
    % Decile sort
    ind = makeUnivSortInd(testSignal, 10, NYSE);
    resBasicSorts(5, count).res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                                                   'weighting', 'v', ...
                                                                   'factorModel', f, ...
                                                                   'printResults', 0, ...
                                                                   'plotFigure',0);
        
    switch f
        % CAPM
        case 1
            factorRet = [mkt];            
            factorTcosts = [mkt_tc];     
        % FF3    
        case 3
            factorRet = [mkt smb hml]; 
            factorTcosts = [mkt_tc smb_tc hml_tc]; 
        % FF4
        case 4
            factorRet = [mkt smb hml umd]; 
            factorTcosts = [mkt_tc smb_tc hml_tc umd_tc]; 
        % FF5
        case 5
            factorRet = [mkt smb hml rmw cma]; 
            factorTcosts = [mkt_tc smb_tc hml_tc rmw_tc cma_tc]; 
        % FF6
        case 6
            factorRet = [mkt smb hml rmw cma umd]; 
            factorTcosts = [mkt_tc smb_tc hml_tc rmw_tc cma_tc umd_tc]; 
    end
    
    % Calculate generalized alphas from Novy-Marx and Velikov (2016)
    nSorts = size(resBasicSorts, 1);
    for j = 1:nSorts        
        anomRet = resBasicSorts(j, count).res.pret(s:e, end);
        anomTcosts = resBasicSorts(j, count).res.tcostsTS(s:e);
        [alpha_res] = calcGenAlpha(anomRet, anomTcosts, factorRet(s:e,:), factorTcosts(s:e,:), 0);
        resBasicSorts(j, count).gen_alpha_res = alpha_res;
    end   
    
    count = count+1;
    
    fprintf('Done with univariate sort controlling for %d-factor model @ %s.\n', f, char(datetime('now')));
    
end


% Sorts conditional on size
nMePtfs = 5;
indME = makeUnivSortInd(me, nMePtfs, NYSE); 


for i = 1:nMePtfs
    tempSignal = testSignal;
    tempSignal(indME ~= i) = nan;
    ind = makeUnivSortInd(tempSignal, 5);
    count = 1;
    for f = [1 3 4 5 6]
        resCondSorts(i,count).res = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                                                     'factorModel', f, ...
                                                                     'printResults', 0, ...
                                                                     'plotFigure', 0);
        count=count+1;
    end    
    fprintf('Done with conditional-on-size sort controlling for size quintile %d @ %s.\n', i, char(datetime('now')));
end


fprintf('\nDone with getting the basic sort results at %s.\n\n', char(datetime('now')));
