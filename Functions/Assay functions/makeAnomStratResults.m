function [resAnoms] = makeAnomStratResults(anoms)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It adds some noise to the anomaly signals and runs univariate
% quintile, value-weighted sorts using NYSE breakpoints.
%------------------------------------------------------------------------------------------
% USAGE:   
% [resAnoms] = makeAnomStratResults(anoms)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - anoms - 3-d numeric array (nMonths x nStocks x nAnoms) with
%                  raw anomaly signals
%------------------------------------------------------------------------------------------
% Output:
%        - resAnoms - vector (nAnoms x 1) of structures containing the
%                     univariate sort results
%------------------------------------------------------------------------------------------
% Examples:
%
% [anoms, labels] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 1, 2);
% [resAnoms] = makeAnomStratResults(anoms)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeUnivSortInd() and runUnivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on getting the anomaly strategy results. Run started at %s.\n\n', char(datetime('now')));

% Load a few variables
load ret
load dates
load me
load tcosts
load NYSE

% Store some dimensions
[nMonths, nStocks, nAnoms] = size(anoms);

% Loop through each anomaly
for i=1:nAnoms
    if mod(i,10) == 0
            fprintf('Done with %d/%d anomalies @ %s.\n', i, nAnoms, char(datetime('now')));
    end
    
    % Add some noise 
    anomSignal = anoms(:,:,i) + randn(nMonths, nStocks)*1e-12;

    % Run a quintile, value-weighted NYSE breakpoints sort
    ind = makeUnivSortInd(anomSignal, 5, NYSE);  
    ind = 1*(ind==1) + 2*(ind==5);
    tempRes = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                               'weighting', 'v', ...
                                               'factorModel',1, ...
                                               'plotFigure', 0, ...
                                               'printResults',0);

    % Assign it to the output structure
    if i==1
        resAnoms = repmat(tempRes, nAnoms, 1);
    else
        resAnoms(i,1) = tempRes;
    end
    
end


fprintf('\nDone with getting the anomaly strategy results at %s.\n\n', char(datetime('now')));
