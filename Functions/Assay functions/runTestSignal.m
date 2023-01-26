function runTestSignal(signalInfo, anoms, labels)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It is a wrapper function that checks all anomalies used for
% benchmarking, runs all the tests, and prints the latex and pdf files.
%------------------------------------------------------------------------------------------
% USAGE:   
% runTestSignal(signalLabel, anoms, labels) 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -signalInfo - a structure containing information about signal from
%                       the website form
%             -signalInfo.Authors - author(s) name(s)
%             -signalInfo.email - corresponding author email address
%             -signalInfo.PaperTitle - paper title
%             -signalInfo.SignalName - signal name
%             -signalInfo.SignalAcronym - signal acronym
%             -signalInfo.fileLink - link to submitted .csv file
%        - anoms - a 3-d numeric array (nMonths x nStocks x nAnoms) with
%                   anomaly signals
%        - labels - a structure with two cell arrays that contain strings 
%                   with short and long label for each anomaly
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% runTestSignal(signalInfo, anoms, labels)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses getAnomStratResults(), getBasicSortsResults(), getRelatedAnomResults(), 
%       getRelatedAnomResults(), makeDendrogramData(), makeCloseAnomResults(), 
%       fillVar(), makeCombStrats(), makeResToPrint(), printTexFile()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Store the signal label
signalLabel = {signalInfo.SignalAcronym};

% Use the getAnomalySignals() to get the signal
[testSignal, ~] = getAnomalySignals(signalInfo.fileLink, 'permno', 'dates');

% Load some variables
load dates
load me
load ret
load NYSE
load ff

% Drop stock/month observations, for which we don't have market cap
testSignal(isnan(me)) = nan;

% Figure out when the signal is available
signalIsFinite = sum(isfinite(testSignal), 2) > 0;
startDateInd   = find(signalIsFinite, 1, 'first');
endDateInd     = find(signalIsFinite, 1, 'last');
timePeriod     = dates([startDateInd endDateInd]);

% Check & fill in the anomalies
[filledAnoms, keepAnoms, keepRollAnoms] = checkFillAnomalies(anoms, me, dates, timePeriod);

% Keep only the anomalies with more than 40% of market cap observations in
% the average month
anoms         = anoms(:, :, keepAnoms);
filledAnoms   = filledAnoms(:, :, keepAnoms);
labels.short  = labels.short(keepAnoms);
labels.long   = labels.long(keepAnoms);
keepRollAnoms = keepRollAnoms(:, keepAnoms);

% Run univariate sorts for all anomalies
resAnoms = makeAnomStratResults(anoms);

% Basic sorts (Tables 1, 2, and 3)
[resBasicSorts, resCondMeSorts] = makeBasicSortsResults(testSignal, timePeriod);

% Calculate anom correlations and run conditional double sorts, and Fama-MacBeths
[resCorrels, resCondSort, resFMBs] = makeAnomBenchmarkResults(anoms, testSignal, timePeriod);

% Calculate the hierarchical agglomerative clustering dendogram ala Jensen et al. (2021)
[Z, dendrogramLabels, cutoff] = makeDendrogramResults(resAnoms, signalLabel, labels.short, resBasicSorts, timePeriod);

% Make closely-related anomaly results
[resCloseFMB, resCloseSpan, closeLabels] = makeCloseAnomResults(resCorrels, resAnoms, anoms, labels, testSignal, resBasicSorts, timePeriod);

% Combination strategies
filledSignal = fillVar(testSignal, me);
combStrats = makeCombStrats(filledAnoms, filledSignal, keepRollAnoms, resAnoms, resBasicSorts, timePeriod);


% Combine all the results in a structure
ResStruct.signalInfo       = signalInfo;
ResStruct.resBasicSorts    = resBasicSorts;
ResStruct.resCondMeSorts   = resCondMeSorts;
ResStruct.resCorrels       = resCorrels;
ResStruct.resAnoms         = resAnoms;
ResStruct.resCondSort      = resCondSort;
ResStruct.resFMBs          = resFMBs;
ResStruct.Z                = Z;
ResStruct.dendrogramLabels = dendrogramLabels;
ResStruct.cutoff           = cutoff;
ResStruct.labels           = labels;
ResStruct.testSignal       = testSignal;
ResStruct.signalLabel      = signalLabel;
ResStruct.timePeriod       = timePeriod;
ResStruct.resCloseFMB      = resCloseFMB;
ResStruct.resCloseSpan     = resCloseSpan;
ResStruct.closeLabels      = closeLabels;
ResStruct.combStrats       = combStrats;

% Create the printable output for the latex document
printResults = makeResToPrint(ResStruct);

% Save the results structure
clearvars -except  ResStruct printResults signalLabel signalInfo
fileName = [char(pwd), filesep, 'Scratch', filesep, 'Assay', filesep, char(signalLabel), '_Results.mat'];
delete(fileName);
save(fileName, 'ResStruct', 'printResults', '-v7.3'); 

% Print the tex files & pdf figures
printTexFile(printResults)

% Send the user an email with the zipped output
sendUserResults(signalInfo)
