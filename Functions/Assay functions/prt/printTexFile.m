function printTexFile(Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the .tex latex file and creates the .pdf figures. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printTexFile(Results)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - Results - structure with results that are used to print the .tex
%                    latex file and .pdf figures
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printTexFile(Results)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses many utility funtions for printing text
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on printing the output files. Run started at %s.\n', char(datetime('now')));

% Choose the path and Latex file name
filePath = [pwd, filesep, 'Scratch', filesep, 'Assay', filesep, 'tex', filesep];
mkdir(filePath);
Results.fileName = [filePath, Results.Text.signalChar, '.tex'];
fclose('all');
delete(Results.fileName);
 
% Open the file for writing
fid = fopen(Results.fileName, 'at');

% Print the header
printDocumentHeader(fid);

% Print the title page
printTitlePage(fid, Results);

% 1. Introduction
printIntroSection(fid, Results)

% 2. Signal diagnostics

% Print the title and text of the section
printSignalDescriptionSection(fid, Results)

% 3. Does it predict returns?

% Print the title and text of the section
printReturnPredictionSection(fid, Results);

% 4. Does it look like anything we've seen?

% Print the title and text of the section
printOtherAnomaliesSection(fid, Results);

% 5. Does it survive the most closely related anoms?

% Print close anomalies section
printCloseAnomsSection(fid, Results);


% 6. Does it add anything to the whole zoo?

% Print combination strategies section
printCombStratsSection(fid, Results);

% Print figures and tables
% Print Figure 1: Signal description
printSignalDescriptionFigure(fid, Results, filePath)

% Print Table 1: Basic sort
printBasicSortTable(fid, Results);

% Print Table 2: Robustness to sorting
printRobustnessToSortingTable(fid, Results);

% Print Table 3: Conditional sort on size
printCondSizeSortTable(fid, Results);

% Print Figure 2: Sharpe ratio distribution
printSharpeDistFigure(fid, Results, filePath);

% Print Figure 3: Ibbotson plots
printIbbotsPlotsFigure(fid, Results, filePath);

% Print Figure 4: Alpha percentiles
printAlphaPrctlFigure(fid, Results, filePath);

% Print Figure 5: Correlations
printCorrelFigure(fid, Results, filePath);

% Print Figure 6: Dendrogram
printDendrogramFigure(fid, Results, filePath);

% Print Figure 7: Conditional Strategies
printCondStratsFigure(fid, Results, filePath);

% Table 4: Fama-MacBeth of closely related anomalies
printCloseAnomsFMBTable(fid, Results)

% Table 5: Spanning tests of closely related anomalies
printCloseAnomsSpanTable(fid, Results)

% Print Figure 8: Conditional Strategies
printCombStratsFigure(fid, Results, filePath);

% Print end of paper text
printEndOfPaperText(fid);

% Print bib file
printBibliographyFile(filePath);

% Timekeeping
fprintf('Printing ended at %s.\n', char(datetime('now')));
