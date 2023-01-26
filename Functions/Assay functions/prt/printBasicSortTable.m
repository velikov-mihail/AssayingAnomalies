function printBasicSortTable(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the basic sort table. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printBasicSortTable(fid, Results)
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
% printBasicSortTable(fid, Results)
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


% Table 1 - basic sort
fprintf(fid, ['\\begin{table}[!htbp]' '\n']);
fprintf(fid, ['\\small' '\n']);
fprintf(fid, ['\\caption{Basic sort: VW, quintile, NYSE-breaks\\\\' '\n']);
fprintf(fid, ['\\small{This table reports average excess returns and alphas for portfolios sorted on ',Results.Text.signalChar, '. ', ...
              'At the end of each month, we sort stocks into five portfolios based on their signal using NYSE breakpoints. ', ...
              'Panel A reports average value-weighted quintile portfolio (L,2,3,4,H) returns in excess of the risk-free rate, ', ...
              'the long-short extreme quintile portfolio (H-L) return, and alphas with respect to the CAPM, ', ...
              '\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} three-factor model augmented with the ', ...
              '\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} five-factor model, and ', ...
              'the \\citet{FamaFrench2015} five-factor model augmented with the \\citet{Carhart1997} momentum factor ', ...
              'following \\citet{FamaFrench2018}. ', ...
              'Panel B reports the factor loadings for the quintile portfolios and long-short extreme quintile portfolio in the ', ...
              '\\citet{FamaFrench2015} five-factor model. ', ...
              'Panel C reports the average number of stocks and market capitalization of each portfolio. ', ...
              'T-statistics are in brackets. The sample period is ', char(num2str(Results.Text.timePeriod(1))), ...
              ' to ', char(num2str(Results.Text.timePeriod(2))), '.}}' '\n']);
fprintf(fid, ['\\label{tab:tsRegs}' '\n']);
fprintf(fid, ['\\begin{tabularx}{\\linewidth}{l*9{>{\\centering\\arraybackslash}X}}\\hline' '\n']);    
% Print Panel A to file
a = Results.Tab_BasicSort.PanelA.a;
tA = Results.Tab_BasicSort.PanelA.tA;
h = Results.Tab_BasicSort.PanelA.h;
fprintf(fid, ['\\multicolumn{7}{l}{Panel A: Excess returns and alphas on ', Results.Text.signalChar, '-sorted portfolios}\\\\[2pt]' '\n']);
fprintf(fid, ['& (L) & (2) & (3) & (4) & (H) & (H-L)\\\\[2pt]' '\n']);    
res = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
fprintf(fid,res);
fprintf(fid, ['\\hline' '\n']);

% Print Panel B to file
a = Results.Tab_BasicSort.PanelB.a;
tA = Results.Tab_BasicSort.PanelB.tA;
h = Results.Tab_BasicSort.PanelB.h;
fprintf(fid, ['\\multicolumn{7}{l}{Panel B: \\citet{FamaFrench2018} 6-factor model loadings for ', Results.Text.signalChar, '-sorted portfolios}\\\\[2pt]' '\n']);
res = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
fprintf(fid,res);
fprintf(fid, ['\\hline' '\n']);

% Print Panel C to file
fprintf(fid, ['\\multicolumn{7}{l}{Panel C: Average number of firms ($n$) and market capitalization ($me$)}\\\\[2pt]' '\n']);
a = Results.Tab_BasicSort.PanelC.a;
h = Results.Tab_BasicSort.PanelC.h;
res = replace(evalc('mat2Tex(a,a,h,0);'),'\',{'\\'});
fprintf(fid,res);
fprintf(fid, ['\\hline' '\n']);

% End of Table 1
fprintf(fid, ['\\end{tabularx}' '\n']);
fprintf(fid, ['\\end{table}' '\n\n\n']);
