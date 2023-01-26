function printSharpeDistFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the Sharpe ratio distribution figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printSharpeDistFigure(fid, Results)
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
% printSharpeDistFigure(fid, Results)
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

% Figure 2
h = figure('Visible','off');
subplot(2,1,1)
histogram(Results.Fig_SharpeDist.PanelA.Hist);
hold on;
line(repmat(Results.Fig_SharpeDist.PanelA.Line, 1, 2), ylim, 'LineWidth', 2, 'Color', 'r');
xlabel('Anomaly Sharpe ratios');
xlim(Results.Fig_SharpeDist.PanelA.xlim)
legend('',Results.Text.signalChar);
hold off;
subplot(2,1,2)
histogram(Results.Fig_SharpeDist.PanelB.Hist);
hold on;
line(repmat(Results.Fig_SharpeDist.PanelB.Line, 1, 2), ylim, 'LineWidth', 2, 'Color', 'r');
xlabel('Anomaly Net Sharpe ratios');
xlim(Results.Fig_SharpeDist.PanelB.xlim)
hold off;
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureSharpeDist.pdf'],'ContentType','vector')    

% Include Figure 2 in the latex document
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\linewidth,keepaspectratio]{',Results.Text.signalChar, '_figureSharpeDist}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Distribution of Sharpe ratios. \\\\' '\n']);
fprintf(fid, ['This figure plots a histogram of Sharpe ratios for ', Results.Text.nAnoms, ...
              ' anomalies, and compares the Sharpe ratio of the ', Results.Text.signalChar, ...
              ' with them (red vertical line). Panel A plots results for gross Sharpe ratios. ', ...
              'Panel B plots results for net Sharpe ratios.' '\n']);
fprintf(fid, ['\\label{fig:distributionSharpeRatios}}' '\n']);          
fprintf(fid, ['\\end{figure}' '\n\n\n']);
