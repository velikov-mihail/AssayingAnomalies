function printOtherAnomaliesSection(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the the Related Anomalies section in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printOtherAnomaliesSection(fid, Results)
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
% printOtherAnomaliesSection(fid, Results)
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
    
% Store a few variables for the text
nAnoms = Results.Text.nAnoms;
signalChar = Results.Text.signalChar;

% Add the section title
fprintf(fid, ['\\section{How does ', signalChar, ' perform relative to the zoo?}  \n']);
fprintf(fid, ['\\label{sec:otherAnoms}' '\n\n\n']);


% Describe Figure 2
grossSharpe = Results.Fig_SharpeDist.PanelA.Line;
grossSharpeAnoms = Results.Fig_SharpeDist.PanelA.Hist;
grossSharpeRank = sprintf('%2.0f', 100*sum(grossSharpe>grossSharpeAnoms)/length(grossSharpeAnoms));

netSharpe = Results.Fig_SharpeDist.PanelB.Line;
netSharpeAnoms = Results.Fig_SharpeDist.PanelB.Hist;
netSharpeRank = sprintf('%2.0f', 100*sum(netSharpe>netSharpeAnoms)/length(netSharpeAnoms));

section_4_text = [ ...
    'Figure~\\ref{fig:distributionSharpeRatios} puts the performance of ', signalChar, ...
    ' in context, showing the long/short strategy performance relative to other ', ...
    'strategies in the ``factor zoo." It shows Sharpe ratio histograms, both for gross ', ...
    'and net returns (Panel A and B, respectively), for ', nAnoms, ' documented ', ...
    'anomalies in the zoo.\\footnote{The anomalies come from March, 2022 release of the \\citet{ChenZimmermann2022} ', ...
    'open source asset pricing dataset. We filter their 207 anomalies and require for each anomaly the average ', ...
    'month to have at least 40\\%% of the cross-sectional observations available for market capitalization on CRSP ', ...
    'in the period for which ', signalChar, ' is available.} ', ...
    'The vertical red line shows where the Sharpe ratio for the ', signalChar, ' strategy ', ...
    'falls in the distribution. The ', signalChar, ' strategy''s gross (net) ', ...
    'Sharpe ratio of ', Results.Text.sharpeChar, ' (',Results.Text.netSharpeChar, ...
    ') is greater than ', grossSharpeRank, '\\%% (', netSharpeRank, ...
    '\\%%) of anomaly Sharpe ratios, respectively. ' '\n\n\n'];
fprintf(fid, section_4_text);  


% Describe Figure 3
pretGrossAnoms = cumprod(1+Results.Fig_Ibbots.pretGrossAnoms)-1;
pretGrossSignal = cumprod(1+Results.Fig_Ibbots.pretGrossTestSignal)-1;
cumGrossRet = sprintf('%.2f', pretGrossSignal(end));
cumGrossRank = sprintf('%.0f', 100*(sum(pretGrossAnoms(end,:) > pretGrossSignal(end))/size(pretGrossAnoms, 2)));

pretNetAnoms = cumprod(1+Results.Fig_Ibbots.pretNetAnoms)-1;
pretNetSignal = cumprod(1+Results.Fig_Ibbots.pretNetTestSignal)-1;
cumNetRet = sprintf('%.2f', pretNetSignal(end));
cumNetRank = sprintf('%.0f', 100*(sum(pretNetAnoms(end,:) > pretNetSignal(end))/size(pretNetAnoms, 2)));

section_4_text = [ ...
    'Figure~\\ref{fig:dollarInvested} plots the growth of a \\$1 invested in these same ', nAnoms, ' anomaly trading strategies (gray lines), ', ...
    'and compares those with the growth of a \\$1 invested in the ', signalChar, ' strategy (red line).', ...
    '\\footnote{The figure assumes an initial investment of \\$1 in T-bills and \\$1 long/short in the ', ...
    'two sides of the strategy. Returns are compounded each month, assuming, as in \\citet*{DetzelNovy-MarxVelikov2022}, ', ...
    'that a capital cost is charged against the strategy''s returns at the risk-free rate. ', ...
    'This excess return corresponds more closely to the strategy''s economic profitability.}     ', ...
    'Ignoring trading costs, a \\$1 invested in the ', signalChar, ' strategy would have yielded ', ...
    '\\$', cumGrossRet,' which ranks the ', signalChar, ' strategy in the top ', ...
    cumGrossRank, '\\%% across the ',nAnoms, ' anomalies. Accounting for trading costs, a \\$1 invested in the ', signalChar, ...
     ' strategy would have yielded \\$', cumNetRet,' which ranks the ', signalChar, ' strategy in the top ', ...
    cumNetRank, '\\%% across the ', nAnoms, ' anomalies.' '\n\n\n'];
fprintf(fid, section_4_text);  


% Describe Figure 4
minGrossRank = sprintf('%.0f', min(Results.Fig_AlphaPrctl.PanelA.dx));
maxGrossRank = sprintf('%.0f', max(Results.Fig_AlphaPrctl.PanelA.dx));

sampleStart = char(num2str(Results.Text.timePeriod(1)));
sampleEnd = char(num2str(Results.Text.timePeriod(2)));

fracZeroFF3NetAlpha = char(num2str(find(Results.Fig_AlphaPrctl.PanelB.y(:,2)>0, 1, 'first')));
fracZeroFF6NetAlpha = char(num2str(find(Results.Fig_AlphaPrctl.PanelB.y(:,5)>0, 1, 'first')));

numPosAlphas = num2words(sum(isfinite(Results.Tab_RobustSort.PanelB.a(1,2:end))));
indPosAlphas = isfinite(Results.Tab_RobustSort.PanelB.a(1,2:end));
minNetRank = sprintf('%.0f', min(Results.Fig_AlphaPrctl.PanelB.dx(indPosAlphas)));
maxNetRank = sprintf('%.0f', max(Results.Fig_AlphaPrctl.PanelB.dx(indPosAlphas)));

section_4_text = [ ...
    'Figure~\\ref{fig:factorModelAlphas} plots percentile ranks for the ', nAnoms, ' anomaly trading ', ...
    'strategies in terms of gross and \\citet{Novy-MarxVelikov2016} net generalized alphas with ', ...
    'respect to the CAPM, and the Fama-French three-, four-, five-, and six-factor ', ...
    'models from Table~\\ref{tab:tsRegs}, and indicates the ranking of the ', signalChar, ' relative to those. ' ... 
    'Panel A shows that the ', signalChar, ' strategy gross alphas fall between the ', minGrossRank, ...
    ' and ', maxGrossRank, ' percentiles across the five factor models. ', ...
    'Panel B shows that, accounting for trading costs, a large fraction of anomalies ', ...
    'have not improved the investment opportunity set of an investor ', ...
    'with access to the factor models over the ', sampleStart, ...
    ' to ', sampleEnd, ' sample. ', ...
    'For example, ', fracZeroFF3NetAlpha, '\\%% (', fracZeroFF6NetAlpha, ...
    '\\%%) of the ', nAnoms, ' anomalies would not have improved the investment ', ...
    'opportunity set for an investor having access to the Fama-French three-factor ', ...
    '(six-factor) model. The ', signalChar, ' strategy has a positive net generalized ', ...
    'alpha for ', numPosAlphas, ' out of the five factor models. In these cases ', ...
    signalChar, ' ranks between the ', minNetRank, ' and ', maxNetRank, ' percentiles ', ...
    'in terms of how much it could have expanded the achievable investment frontier.' '\n\n\n'];
fprintf(fid, section_4_text);  
