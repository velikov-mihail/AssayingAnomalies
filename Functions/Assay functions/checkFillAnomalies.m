function [anoms, keepAnoms, keepRollAnoms] = checkFillAnomalies(anoms, me, dates, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It checks and fills in the anomalies used for
% benchmarking a test signal in the protocol of tests for evaluating new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It ensures that there are more than 40% of market observations
% either in the average month (keepAnoms) or over the past 10 years
% (keepRollAnoms).
%------------------------------------------------------------------------------------------
% USAGE:   
% [filledAnoms, keepAnoms, keepRollAnoms] = checkFillAnomalies(anoms, me, dates, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - anoms - 3-d numeric array (nMonths x nStocks x nAnoms) with
%                  raw anomaly signals
%        - me - matrix (nMonths x nStocks) with market capitalization
%               values
%        - dates - vector with dates in YYYYMM format
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%------------------------------------------------------------------------------------------
% Output:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - keepAnoms - vector (nAnoms x 1) indicating which anomalies to
%                      keep
%        - keepRollAnoms - matrix (nMonths x nAnoms) indicating whether an
%                          anomaly has had more than 40% of market cap
%                          observations in the average month over the past
%                          10 years.
%------------------------------------------------------------------------------------------
% Examples:
%
% [anoms, labels] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 1, 2);
% [filledAnoms, keepAnoms, keepRollAnoms] = checkFillAnomalies(anoms, me, dates, [197501 202112])
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

fprintf('\nNow working on checking the anomalies. Run started at %s.\n\n', char(datetime('now')));

N = 120;
mcapThresh = 0.40;


[nMonths, ~, nAnoms] = size(anoms);
keepAnoms = false(nAnoms, 1);
keepRollAnoms = false(nMonths, nAnoms);

for i=1:nAnoms
    if mod(i,10)==0
            fprintf('Done with %d/%d anomalies @ %s.\n', i, nAnoms, char(datetime('now')));
    end
    % Get the anomaly
    var = anoms(:,:,i);

    % Add some white noise to it to allow for sorting & percentile
    % calculation
    var = var+randn(size(var))*1e-12;

    % Kick out stocks/months with no market cap
    var(~isfinite(me)) = nan;    
    
    % Determine the period it's available 
    indMthsWithObs = sum(isfinite(var), 2) > 0;        
    s = max( find(dates==timePeriod(1)), find(indMthsWithObs, 1, 'first'));
    e = min( find(dates==timePeriod(2)), find(indMthsWithObs, 1, 'last'));    
    
    % If we have at least 10 years
    if e > s+N
        
        % Determine if we have, on average, observations for this variable
        % that are more than 40% of the number of observations for market
        % cap
                
        % Determine the monthsin which we have data for this variable in
        % the time period chosen by user
        indMthsWithObsInSample = (indMthsWithObs & ...
                                  dates >= dates(s) & ...
                                  dates <= dates(e));
        
        % Store the number of fininte observations for var and me                          
        numFiniteVar = sum(isfinite(var+me), 2);
        numFiniteMe = sum(isfinite(me), 2);
        
        % Calculate the average fraction of market cap observations
        prctOfMktCapObs =  numFiniteVar ./  numFiniteMe;
        meanPrctOfMktCapObs = mean(prctOfMktCapObs(indMthsWithObsInSample));
        
        % Check if keep the anomaly
        keepAnoms(i,1) = (meanPrctOfMktCapObs > mcapThresh);   
        
        % If true, fill it in
        if keepAnoms(i)                    
            anoms(:, :, i) = fillVar(var, me);
            for r = s+N:e
                keepRollAnoms(r, i) = mean(prctOfMktCapObs(r-N+1:r)) > mcapThresh;
            end
        end
    end

        
end

fprintf('\nDone with checking the anomalies at %s.\n\n', char(datetime('now')));
