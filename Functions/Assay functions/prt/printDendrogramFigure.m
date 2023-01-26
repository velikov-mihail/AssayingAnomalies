function printDendrogramFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the alpha percentiles figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printDendrogramFigure(fid, Results)
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
% printDendrogramFigure(fid, Results)
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

% Store the number of anomalies
nAnoms = length(Results.Fig_Dendrogram.dendrogramLabels);

% Create & save Figure 6
h = figure('Visible','off');
dendrogram(Results.Fig_Dendrogram.Z, nAnoms, 'Labels', Results.Fig_Dendrogram.dendrogramLabels, ...
                                             'ColorThreshold' , Results.Fig_Dendrogram.cutoff);
xtickangle(90)
set(gca,'FontSize',8);
set(gcf, 'PaperPositionMode', 'auto');
set(gcf,'units','normalized','outerposition',[0 0 1 1]);
set(gca,'LooseInset',get(gca,'TightInset'))
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureDendrogram.pdf'],'ContentType','vector')    

% Include Figure 6 in the latex document
fprintf(fid, ['\\begin{landscape}' '\n']);
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\linewidth,keepaspectratio]{', Results.Text.signalChar, '_figureDendrogram}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Agglomerative hierarchical cluster plot\\\\' '\n']);
fprintf(fid, ['This figure plots an agglomerative hierarchical cluster plot using Ward''s minimum ', ...
              'method and a maximum of 10 clusters. ' '\n']);
fprintf(fid, ['\\label{fig:hierarchicalClusterPlot}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n']);
fprintf(fid, ['\\end{landscape}' '\n\n\n']);
