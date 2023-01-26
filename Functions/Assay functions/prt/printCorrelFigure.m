function printCorrelFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the alpha percentiles figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCorrelFigure(fid, Results)
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
% printCorrelFigure(fid, Results)
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

% Create & save Figure 5
h=figure('Visible','off');
subplot(2,1,1)
plotNameHistogram(Results.Fig_Correls.PanelA.x, Results.Fig_Correls.PanelA.lbl);
xlabel('Panel A: Pearson');
subplot(2,1,2)
plotNameHistogram(Results.Fig_Correls.PanelB.x, Results.Fig_Correls.PanelB.lbl);
xlabel('Panel B: Spearman');
set(gcf,'position', [      965   200   588   1407])
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureCorrel.pdf'],'ContentType','vector')    

% Include Figure 5 in the latex document
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[height=0.85\\textheight,keepaspectratio]{', Results.Text.signalChar, '_figureCorrel}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Distribution of correlations. \\\\' '\n']);
fprintf(fid, ['This figure plots a name histogram of correlations of ', Results.Text.nAnoms, ...
              ' anomaly signals with ', Results.Text.signalChar, '. ', ...
              'The correlations are pooled. Panel A plots Pearson correlations, while Panel B plots ', ...
              'Spearman rank correlations.' '\n']);
fprintf(fid, ['\\label{fig:distributionCorrelations}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n\n\n']);
