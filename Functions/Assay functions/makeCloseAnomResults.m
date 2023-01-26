function [resCloseFMB, resCloseSpan, closeLabels] = makeCloseAnomResults(resCorrels, resAnoms, anoms, labels, testSignal, resBasicSorts, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It finds the most-closely related anomalies and runs Fama-MacBeth
% regressions and spanning tests controlling for them.
%------------------------------------------------------------------------------------------
% USAGE:   
% [resCloseFMB, resCloseSpan, closeLabels] = makeCloseAnomResults(resCorrels, resAnoms, anoms, labels, testSignal, resBasicSorts, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - resCorrels - numeric matrix (nAnoms x 2) containing the
%                       correlation results
%        - resAnoms - vector (nAnoms x 1) of structures containing the
%                     univariate sort results
%        - anoms - 3-d numeric array (nMonths x nStocks x nAnoms) with
%                  raw anomaly signals
%        - labels - a structure with two cell arrays that contain strings 
%                   with short and long label for each anomaly
%        - testSignal - a matrix (nMonths x nStocks) with the proposed
%                       anomaly signal
%        - resBasicSorts - vector (nAnoms x 1) of structures with univariate
%                          sort results
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - resCloseFMB - vector of structures (nCLoseAnoms+1 x 1) 
%                        containing the Fama-Macbeth results controlling 
%                        for the closely-related anomalies
%        - resCloseSpan - vector of structures (nCLoseAnoms+1 x 1) 
%                         containing the spanning test results controlling  
%                         for the closely-related anomalies
%        - closeLabels - a structure with two cell arrays that contain  
%                        strings with short and long label for each
%                        closely-related anomaly
%------------------------------------------------------------------------------------------
% Examples:
%
% [resCloseFMB, resCloseSpan, closeLabels] = makeCloseAnomResults(resCorrels, resAnoms, anoms, labels, testSignal, resBasicSorts, timePeriod)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses nanols() and runFamaMacBeth()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on getting the closely-related anomaly results. Run started at %s.\n', char(datetime('now')));

% Load a few variables
load dates
load ff
load ret

% Find the start and end date
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Store the number of anomalies
nAnoms = size(anoms, 3);

% Initialize the R2 and Correlation vectors
spanR2 = nan(nAnoms, 1);
anomCorr = nan(nAnoms, 1);

% Get the spanning results first
for i=1:nAnoms
    if ~isempty(resAnoms(i).xret)
        y = resBasicSorts(1,1).res.pret(s:e,end);
        X = [ones(size(y)) resAnoms(i).pret(s:e,end)];
        res = nanols(y, X);
        spanR2(i,1) = res.rbar;                                            % R2 from return regression.
        anomCorr(i,1) = resCorrels(i,2);                                   % Cross-sectional signal correlation
    end
end

% Combine the ranks based on R2 and correlation
combinedRank = tiedrank(spanR2) + tiedrank(abs(anomCorr));

% Sort based on the combined rank
[~, I] = sort(combinedRank, 'descend');

% Pick the number of close anomalies
nCloseAnoms = 6;

% Store the returns to the test signal strategy
y = resBasicSorts(1,1).res.pret(s:e,end);

% Initialize the spanning
spanX = [];
fmbX = [];

% Loop through the close anomalies
for i = 1:nCloseAnoms
    % Choose the anomaly signal and add some noise to it
    anomSignal = anoms(:,:,I(i));

    % Run a Fama-MacBeth regression controlling for this close signal
    resCloseFMB(i, 1) = runFamaMacBeth(ret, [testSignal anomSignal], dates, 'timePeriod', timePeriod, ...
                                                                            'printResults', 0);    
    % Add it for the one controlling for all close signals
    fmbX = [fmbX anomSignal];
    
    % Make the RHS for the spanning tests & run it
    X = [ones(size(y)) resAnoms(I(i)).pret(s:e,end) ff6(s:e, 2:end)];
    resCloseSpan(i, 1) = nanols(y, X);
    
    % Add it for the one controlling for all close signals
    spanX = [spanX resAnoms(I(i)).pret(s:e,end)];
end

% Add the Fama-MacBeth with all
resCloseFMB(nCloseAnoms+1, 1) = runFamaMacBeth(ret, [testSignal fmbX], dates, 'timePeriod', timePeriod, ...
                                                                          'printResults', 0);    

% Add the spanning test with all
X = [ones(size(y)) spanX ff6(s:e, 2:end)];
resCloseSpan(nCloseAnoms+1, 1) = nanols(y, X);

% Store the close labels 
closeLabels.short = labels.short(I(1:nCloseAnoms));                         
closeLabels.long = labels.long(I(1:nCloseAnoms));                         

% Timekeeping
fprintf('\nDone with closely-related anomaly results at %s.\n\n', char(datetime('now')));
