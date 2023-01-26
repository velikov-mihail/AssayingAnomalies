function printRobustnessToSortingTable(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the robustness to sorting table. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printRobustnessToSortingTable(fid, Results)
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
% printRobustnessToSortingTable(fid, Results)
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



% Table 2 - robustness to sorting
fprintf(fid, ['\\begin{table}[!htbp]' '\n']);
fprintf(fid, ['\\small' '\n']);
fprintf(fid, ['\\caption{Robustness to sorting methodology \\& trading costs\\\\' '\n']);
fprintf(fid, ['\\small{This table evaluates the robustness of the choices made in the ',Results.Text.signalChar, ' strategy construction methodology. ', ...
              'In each panel, the first row shows results from a quintile, value-weighted sort using NYSE break points as employed in Table~\\ref{tab:tsRegs}. ', ...
              'Each of the subsequent rows deviates in one of the three choices at a time, and the choices are specified in the first three columns. ', ...
              'For each strategy construction methodology, the table reports average excess returns and alphas with respect to the CAPM,  ', ...
              '\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} three-factor model augmented with the ', ...
              '\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} five-factor model, and ', ...
              'the \\citet{FamaFrench2015} five-factor model augmented with the \\citet{Carhart1997} momentum factor ', ...
              'following \\citet{FamaFrench2018}. ', ...
              'Panel A reports average returns and alphas with no adjustment for trading costs. ', ...
              'Panel B reports net average returns and \\citet{Novy-MarxVelikov2016} generalized alphas as ', ...
              'prescribed by \\citet*{DetzelNovy-MarxVelikov2022}. ', ...
              'T-statistics are in brackets. The sample period is ', char(num2str(Results.Text.timePeriod(1))), ...
              ' to ', char(num2str(Results.Text.timePeriod(2))), '.}}' '\n']);
fprintf(fid, ['\\label{tab:robustnessToSorting}' '\n']);
fprintf(fid, ['\\begin{tabularx}{\\linewidth}{l*9{>{\\centering\\arraybackslash}X}}\\hline' '\n']);    

% Panel A: Gross returns
a = Results.Tab_RobustSort.PanelA.a;
tA = Results.Tab_RobustSort.PanelA.tA;
h = Results.Tab_RobustSort.PanelA.h;
fprintf(fid, ['\\multicolumn{9}{l}{Panel A: Gross Returns and Alphas}\\\\[2pt]' '\n']);
fprintf(fid, ['Portfolios & Breaks & Weights & $r^e$ & $\\alpha_{\\text{CAPM}}$  & $\\alpha_{\\text{FF3}}$ & $\\alpha_{\\text{FF4}}$  & $\\alpha_{\\text{FF5}}$  & $\\alpha_{\\text{FF6}}$\\\\[2pt]' '\n']);
textToPrt = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
textToPrt = replace(textToPrt, '[-1pt]','[-1pt] & &');
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% Panel B: Net returns
a = Results.Tab_RobustSort.PanelB.a;
tA = Results.Tab_RobustSort.PanelB.tA;
h = Results.Tab_RobustSort.PanelB.h;
fprintf(fid, ['\\multicolumn{9}{l}{Panel B: Net Returns and \\citet{Novy-MarxVelikov2016} generalized alphas}\\\\[2pt]' '\n']);
fprintf(fid, ['Portfolios & Breaks & Weights & $r^e_{net}$ & $\\alpha^*_{\\text{CAPM}}$  & $\\alpha^*_{\\text{FF3}}$ & $\\alpha^*_{\\text{FF4}}$  & $\\alpha^*_{\\text{FF5}}$  & $\\alpha^*_{\\text{FF6}}$\\\\[2pt]' '\n']);
textToPrt = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
textToPrt = replace(textToPrt, '[-1pt]','[-1pt] & &');
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% End of Table 2
fprintf(fid, ['\\end{tabularx}' '\n']);
fprintf(fid, ['\\end{table}' '\n\n\n']);

