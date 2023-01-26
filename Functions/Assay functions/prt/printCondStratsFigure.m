function printCondStratsFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the conditional strategies figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCondStratsFigure(fid, Results)
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
% printCondStratsFigure(fid, Results)
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

% Create & save Figure 7
h=figure('Visible','off');
subplot(3,1,1)
histogram(Results.Fig_CondAnoms.PanelA.Hist);
xlabel('Panel A: T-stats from Fama-MacBeths');
subplot(3,1,2)
histogram(Results.Fig_CondAnoms.PanelB.Hist);
xlabel('Panel B: T-stats from spanning tests');
subplot(3,1,3)
histogram(Results.Fig_CondAnoms.PanelC.Hist);
xlabel('Panel C: T-stats from conditional sorts');
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureCondStrats.pdf'],'ContentType','vector')    

% Include Figure 7 in the latex document
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\linewidth,keepaspectratio]{', Results.Text.signalChar, '_figureCondStrats}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Distribution of t-stats on conditioning strategies\\\\' '\n']);
fprintf(fid, ['\\small{This figure plots histograms of t-statistics for predictability tests of ', Results.Text.signalChar, ' ', ...
              'conditioning on each of the ', Results.Text.nAnoms, ' anomaly signals one at a time. ', ...
              'Panel A reports t-statistics on $\\beta_{', Results.Text.signalChar, '}$', ...
              ' from Fama-MacBeth regressions of the form $r_{i,t} = \\alpha + \\beta_{', Results.Text.signalChar, '}', ...
              Results.Text.signalChar, '_{i,t} + \\beta_X X_{i,t}+\\epsilon_{i,t}$, ', ...
              'where $X$ stands for one of the ', Results.Text.nAnoms, ' anomaly signals at a time. ', ...
              'Panel B plots t-statistics on $\\alpha$ from spanning tests of the form: ', ...
              '$r_{',Results.Text.signalChar, ', t} = \\alpha + \\beta r_{X, t}+\\epsilon_t$, ', ...
              'where $r_{X,t}$ stands for the returns to one of the ', Results.Text.nAnoms, ' anomaly trading strategies at a time. ', ...                  
              'The strategies employed in the spanning tests are constructed using quintile sorts, value-weighting, and NYSE breakpoints. ', ...
              'Panel C plots t-statistics on the average returns to strategies constructed by conditional double sorts. ', ...
              'In each month, we sort stocks into quintiles based one of the ', Results.Text.nAnoms, ...
              ' anomaly signals at a time. Then, within each quintile, ', ...
              'we sort stocks into quintiles based on ', Results.Text.signalChar, '. Stocks are finally grouped into ', ...
              'five ', Results.Text.signalChar, ' portfolios by combining stocks within each anomaly sorting portfolio. ', ...
              'The panel plots the t-statistics on the average returns of these conditional double-sorted ', Results.Text.signalChar, ...
              ' trading strategies conditioned on each of the 157 anomalies. }' '\n']);
fprintf(fid, ['\\label{fig:conditionalStrategies}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n\n\n']);
