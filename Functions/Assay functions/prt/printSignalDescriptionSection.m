function printSignalDescriptionSection(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the the Signal Description section in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printSignalDescriptionSection(fid, Results)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - fid - file ID for writing
%        - Results - structure with results that are used to print the .tex
%                    latex file and .pdf figures
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printSignalDescriptionSection(fid, Results)
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


% Load the dates
load dates
     
% Add the sectoin title
fprintf(fid, ['\\section{Signal diagnostics} \n']);
fprintf(fid, ['\\label{sec:signalDescription}' '\n\n\n']);

% Determine the sample
s = find(dates==Results.Text.timePeriod(1));
e = find(dates==Results.Text.timePeriod(2));

% Store some results for the text
signalChar = Results.Text.signalChar;
signalMean = sprintf('%2.2f', mean(Results.Fig_Cov.PanelA.y(s:e,end), 'omitnan'));
signalMedian = sprintf('%2.2f', mean(Results.Fig_Cov.PanelA.y(s:e,2), 'omitnan'));
signalIQR_LB = sprintf('%2.2f', min(Results.Fig_Cov.PanelA.y(s:e,1), [], 'omitnan'));
signalIQR_UB = sprintf('%2.2f', max(Results.Fig_Cov.PanelA.y(s:e,3), [], 'omitnan'));
sampleStart = sprintf('%d', floor(Results.Text.timePeriod(1)/100));
sampleEnd = sprintf('%d', floor(Results.Text.timePeriod(2)/100));
avgCoverageNames = sprintf('%2.2f', 100*mean(Results.Fig_Cov.PanelB.y(s:e,1), 'omitnan'));
avgCoverageMktCap = sprintf('%2.2f', 100*mean(Results.Fig_Cov.PanelB.y(s:e,2), 'omitnan'));

% Add the text
section_2_1_text = [ ...
    'Figure~\\ref{fig:descriptiveStats}  plots descriptive statistics for the ', ...
    signalChar, ' signal. Panel A plots the time-series of the mean, median, and interquartile range for ', signalChar, '. ', ...
    'On average, the cross-sectional mean (median) ', signalChar, ' is ', signalMean, ' (', signalMedian, ') ', ...
    ' over the ', sampleStart, ' to ', sampleEnd, ' sample, where the starting date ', ...
    'is determined by the availability of the input ', signalChar, ' data. The signal''s ', ...
    'interquartile range spans ', signalIQR_LB, ' to ', signalIQR_UB, '. ', ...
    'Panel B of Figure~\\ref{fig:descriptiveStats} plots the time-series of the coverage of the ', signalChar, ' ', ...
    'signal for the CRSP universe. On average, the ', signalChar, ' signal is available for ', avgCoverageNames, '\\%% of CRSP names, ' ...
    ' which on average make up ', avgCoverageMktCap, '\\%% ', 'of total market capitalization.' '\n\n\n'];
fprintf(fid, section_2_1_text);  
