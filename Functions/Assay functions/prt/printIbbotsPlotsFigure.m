function printIbbotsPlotsFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the Ibbotson plot figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printIbbotsPlotsFigure(fid, Results)
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
% printIbbotsPlotsFigure(fid, Results)
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

% Figure 3
h = figure('Visible','off');
nAnoms = size(Results.Fig_Ibbots.pretGrossAnoms, 2);
subplot(2,1,1)
colororder([repmat([0.8 0.8 0.8], nAnoms, 1); [1 0 0]]);
for i = 1:nAnoms
    cumRetsAnoms = ibbots(Results.Fig_Ibbots.pretGrossAnoms, Results.Fig_Ibbots.dates);    
end

hold on;
cumRetsTestSignal = ibbots(Results.Fig_Ibbots.pretGrossTestSignal, Results.Fig_Ibbots.dates);

ylim([min(min([cumRetsAnoms cumRetsTestSignal])) max(max([cumRetsAnoms cumRetsTestSignal]))])
legend(['Anomalies',repmat({''}, 1, nAnoms-1),Results.Text.signalChar],'Location','Northwest');
title('Gross returns');
hold off;


subplot(2,1,2)
colororder([repmat([0.8 0.8 0.8], nAnoms, 1); [1 0 0]]);
for i = 1:nAnoms
    cumRetsAnoms = ibbots(Results.Fig_Ibbots.pretNetAnoms, Results.Fig_Ibbots.dates);    
end

hold on;
cumRetsTestSignal = ibbots(Results.Fig_Ibbots.pretNetTestSignal, Results.Fig_Ibbots.dates);

ylim([min(min([cumRetsAnoms cumRetsTestSignal])) max(max([cumRetsAnoms cumRetsTestSignal]))])
title('Net returns');
hold off;
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureIbbots.pdf'],'ContentType','vector')    

% Include Figure 3 in the latex document
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\linewidth,keepaspectratio]{', Results.Text.signalChar, '_figureIbbots}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Dollar invested. \\\\' '\n']);
fprintf(fid, ['This figure plots the growth of a \\$1 invested in ', Results.Text.nAnoms, ...
              ' anomaly trading strategies (gray lines), and compares those with the ', Results.Text.signalChar, ...
              ' trading strategy (red line). The strategies are constructed using value-weighted ', ...
              'quintile sorts using NYSE breakpoints. Panel A plots results for gross strategy returns. ', ...
              'Panel B plots results for net strtaegy returns.' '\n']);
fprintf(fid, ['\\label{fig:dollarInvested}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n\n\n']);
