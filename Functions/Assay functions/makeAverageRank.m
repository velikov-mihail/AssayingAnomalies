function eret = makeAverageRank(filledAnoms,me) 
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% average rank as the method and runs univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% eret = makeAverageRank(filledAnoms,me) 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - me - numeric matrix (nMonths x nStocks) with market
%               capitalization
%------------------------------------------------------------------------------------------
% Output:
%        - eret - numeric matrix (nMonths x nStocks) with forecast returns
%------------------------------------------------------------------------------------------
% Examples:
%
% eret = makeAverageRank(filledAnoms,me);
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

% Timekeeping
fprintf('\nNow working on average rank with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));

% Average rank
eret = sum(filledAnoms,3);
eret(isnan(me)) = nan;

% Timekeeping
fprintf('Done with average rank at %s.\n',char(datetime('now')));