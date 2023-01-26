function [iret, ireta] = makeIndustryReturns(FFind)
% PURPOSE: This function creates and stores the value-weighted returns for
% an FF industries indicator
%------------------------------------------------------------------------------------------
% USAGE:   
% [iret, ireta] = makeIndustryReturns(FFind)             
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -FFind - matrix (nMonths x nStocks) with the FF industries indicators
%------------------------------------------------------------------------------------------
% Output:
%        -iret - matrix (nMonths x nInds) with the industry returns
%        -ireta - matrix (nMonths x nStocks) with assigned industry returns
%                 to stock/month observations
%------------------------------------------------------------------------------------------
% Examples:
%
% [iFF49ret, iFF49reta] = makeIndustryReturns(FF49)
% [iFF17ret, iFF17reta] = makeIndustryReturns(FF17)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires makeIndustryClassifications() to have been run.
%       Uses runUnivSort(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Load the variables
load ret
load me
load dates

% Store a few constants
nInds = max(max(FFind));
nStocks = size(ret, 2);

% Run a univariate sort using the FF49 industry index
res = runUnivSort(ret, FFind, dates, me, 'factorModel', 1, ...
                                        'printResults', 0, ...
                                        'plotFigure', 0, ...
                                        'addLongShort',0); 

% Store the industry portfolio returns
iret = res.pret(:,1:nInds);

% Assign the industry portfolio returns to individual stocks 
ireta = nan(size(ret));
for i = 1:nInds
    rptdIret = repmat(iret(:,i), 1, nStocks);
    ireta(FFind==i) = rptdIret(FFind==i);
end
