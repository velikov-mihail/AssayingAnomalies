function [resCorrels, resCondSort, resFMBs] = makeAnomBenchmarkResults(anoms, testSignal, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It adds some noise to the anomaly signals and benchmarks the
% anomaly performances through calculating correlations and running
% conditional double sorts and Fama-MacBeth regressions.
%------------------------------------------------------------------------------------------
% USAGE:   
% [resCorrels, resCondSort, resFMBs] = makeAnomBenchmarkResults(anoms, testSignal, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - anoms - 3-d numeric array (nMonths x nStocks x nAnoms) with
%                  raw anomaly signals
%        - testSignal - a matrix (nMonths x nStocks) with the proposed
%                       anomaly signal
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - resCorrels - numeric matrix (nAnoms x 2) containing the
%                       correlation results
%        - resCondSort - vector (nAnoms x 1) of structures containing the
%                        conditional sort results
%        - resFMBs - vector (nAnoms x 1) of structures containing the
%                    Fama-MacBeth results
%------------------------------------------------------------------------------------------
% Examples:
%
% [anoms, labels] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 1, 2);
% [resCorrels, resCondSort, resFMBs] = makeAnomBenchmarkResults(anoms, mpe, [197501 202112])
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses calcPanelCorrels(), makeBivSortInd(), runUnivSort(),
%       runFamaMacBeth()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on getting the related anomalies results. Run started at %s.\n\n', char(datetime('now')));

% Load some variables we'll need
load ret
load dates
load me
load tcosts
load NYSE

% Find the index of the start and end dates
s = find(dates == timePeriod(1));
e = find(dates == timePeriod(2));

% Store a few constants
[nMonths, nStocks, nAnoms] = size(anoms);

% Initializethe correlations matrix
resCorrels = nan(nAnoms,2);

% Loop over the anomalies
for i=1:nAnoms
    
    % Timekeeping
    if mod(i,10) == 0
            fprintf('Done with %d/%d anomalies @ %s.\n', i, nAnoms, char(datetime('now')));
    end

    % Calculate the correlations
    resCorrels(i, :) = calcPanelCorrels(anoms(s:e, :, i), testSignal(s:e, :));
    
    % Add some noise to the signal and run the conditional double sorts
    anomSignal = anoms(:, :, i) + randn(nMonths, nStocks)*1e-12;
    ind = makeBivSortInd(anomSignal, 5, ...
                         testSignal, 5, ...
                         'sortType', 'conditional');   
    ind = 1 * ismember(ind, 1:5:21) + ...
          2 * ismember(ind, 5:5:25);
    tempResCondSort = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                                       'factorModel', 1, ...
                                                       'timePeriod', timePeriod, ...
                                                       'plotFigure', 0, ...
                                                       'printResults', 0);               
    
    % Assign it to the output structure
    if i==1
        resCondSort = repmat(tempResCondSort, nAnoms, 1);
    else
        resCondSort(i,1) = tempResCondSort;
    end


    % Run the Fama-MacBeth regressions
    tempResFMBs = runFamaMacBeth(100*ret, [testSignal anoms(:, :, i)], dates, 'printResults', 0, ...
                                                                          'timePeriod', timePeriod);

    % Assign it to the output structure
    if i==1
        resFMBs = repmat(tempResFMBs, nAnoms, 1);
    else
        resFMBs(i,1) = tempResFMBs;
    end    
end

% Timekeeping
fprintf('\nDone with getting the related anomalies results at %s.\n\n', char(datetime('now')));
