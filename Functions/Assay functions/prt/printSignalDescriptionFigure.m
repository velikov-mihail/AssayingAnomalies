function printSignalDescriptionFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the signal description figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printSignalDescriptionFigure(fid, Results)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - fid - file ID for writing
%        - Results - structure with results that are used to print the .tex
%                    latex file and .pdf figures
%        - filePath - the file path where the figure is to be stored
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printSignalDescriptionFigure(fid, Results)
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


% Create & save Figure 1
h = figure('Visible','off');
subplot(2,1,1);
plot(Results.Fig_Cov.PanelA.x, Results.Fig_Cov.PanelA.y)
legend('25th','Median','75th','Mean','Location','Southeast');
title(['Panel A: ', Results.Text.signalChar, ' percentiles']);
xlim(Results.Fig_Cov.PanelA.xlim)
subplot(2,1,2);
plot(Results.Fig_Cov.PanelB.x, Results.Fig_Cov.PanelB.y)
legend('% of names','% of market cap','Location','Southeast');
title(['Panel B: ', Results.Text.signalChar, ' coverage']);
xlim(Results.Fig_Cov.PanelB.xlim)
export_fig(h,[filePath, Results.Text.signalChar, '_figureSignalDescription.pdf'],'-transparent');

% Include the Figure in the latex document
fprintf(fid, ['\\newpage' '\n']);
fprintf(fid, ['\\clearpage' '\n\n']);
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\textwidth,keepaspectratio]{',Results.Text.signalChar, '_figureSignalDescription}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Times series of ', Results.Text.signalChar, ' percentiles and coverage. \\\\' '\n']);
fprintf(fid, ['This figure plots descriptive statistics for ', Results.Text.signalChar, '. ', ...
              'Panel A shows cross-sectional percentiles of ', Results.Text.signalChar, ' over the sample. ', ...
              'Panel B plots the monthly coverage of ', Results.Text.signalChar, ' relative to ', ...
              'the universe of CRSP stocks with available market capitalizations.' '\n']);
fprintf(fid, ['\\label{fig:descriptiveStats}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n\n\n']);
