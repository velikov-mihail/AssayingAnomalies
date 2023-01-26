function filledVar = fillVar(var, me)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It standardizes and fills in with the cross-sectional median all
% missing observations in an anomaly signal matrix (var), for which there 
% is an observation for market capitalization (me).
%------------------------------------------------------------------------------------------
% USAGE:   
% filledVar = fillVar(var, me)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - var - matrix (nMonths x nStocks) to be filled in
%        - me - matrix (nMonths x nStocks) with market capitalization
%               values
%------------------------------------------------------------------------------------------
% Output:
%        - filledVar - matrix (nMonths x nStocks) with filled-in
%                      observations
%------------------------------------------------------------------------------------------
% Examples:
%
%   filledVar = fillVar(var, me)
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Check if the updating frequency is less than monthly
varNumFinite = sum(isfinite(var), 2);
indMthsWithObs = find(varNumFinite > 0);
if mode(indMthsWithObs - lag(indMthsWithObs, 1, nan)) ~= 1
    var = FillMonths(var);
end    

% Create a monthly rank and standardize to be between -0.5 and 0.5
var = tiedrank(var')';
var = (var - 1) ./ (max(var, [], 2)-1);
var = var - 0.5;        

% Fill the observations with market with the median for this
% characteristic (i.e., 0)
indToZero = isnan(var) & isfinite(me);    
var(indToZero) = 0;

% Set to NaN all observations where we don't have a market cap
var(isnan(me)) = nan;

% Assign to the new 3-d array
filledVar = var;      
