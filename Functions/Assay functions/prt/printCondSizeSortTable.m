function printCondSizeSortTable(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the conditional sort on size table. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCondSizeSortTable(fid, Results)
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
% printCondSizeSortTable(fid, Results)
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

% Table 3 - Conditional sort on size and signal
fprintf(fid, ['\\begin{landscape}' '\n']);
fprintf(fid, ['\\begin{table}[!htbp]' '\n']);
fprintf(fid, ['\\small' '\n']);
fprintf(fid, ['\\caption{Conditional sort on size and ', Results.Text.signalChar, '\\\\' '\n']);
fprintf(fid, ['\\small{This table presents results for conditional double sorts on size and ', Results.Text.signalChar, '. ', ... 
               'In each month, stocks are first sorted into quintiles based on size using NYSE breakpoints. ', ...
               'Then, within each size quintile, stocks are further sorted based on ', Results.Text.signalChar, '. ', ...
               'Finally, they are grouped into twenty-five portfolios based on the intersection of the two sorts. ', ...
               'Panel A presents the average returns to the 25 portfolios, as well as strategies that go ', ...
               'long stocks with high ',Results.Text.signalChar, ' and short stocks with low ',Results.Text.signalChar, ... 
               ' .Panel B documents the average number of firms ', ...
               ' and the average firm size for each portfolio. The sample period is ', char(num2str(Results.Text.timePeriod(1))), ...
              ' to ', char(num2str(Results.Text.timePeriod(2))), '.}}' '\n']);
fprintf(fid, ['\\label{tab:doubleSortSize}' '\n']);
fprintf(fid, ['\\begin{tabularx}{\\linewidth}{l*7{>{\\centering\\arraybackslash}X}*7{>{\\centering\\arraybackslash}X}}\\hline' '\n']);

% Panel A: Averge returns and strategy results
fprintf(fid, ['\\multicolumn{13}{l}{Panel A: portfolio average returns and time-series regression results}\\\\[2pt]' '\n']);
a = Results.Tab_CondSizeSort.PanelA.a;
tA = Results.Tab_CondSizeSort.PanelA.tA;
h = Results.Tab_CondSizeSort.PanelA.h;
fprintf(fid, ['& & \\multicolumn{5}{c}{', Results.Text.signalChar, ' Quintiles} & & \\multicolumn{6}{c}{', Results.Text.signalChar, ' Strategies} \\\\[2pt]' '\n']);
fprintf(fid, ['& & (L) & (2) & (3) & (4) & (H) & & $r^e$ & $\\alpha_{CAPM}$ & $\\alpha_{FF3}$ & $\\alpha_{FF4}$  & $\\alpha_{FF5}$ &$\\alpha_{FF6}$\\\\\\cline{3-7}\\cline{9-14}' '\n']);
fprintf(fid, ['\\parbox[t]{2mm}{\\multirow{10}{*}{\\rotatebox[origin=c]{90}{Size quintiles }}} ' '\n']);
textToPrt = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
textToPrt=[textToPrt(1:101) '&'  textToPrt(102:311) '&' textToPrt(312:520) '&' textToPrt(521:730) '&' textToPrt(731:940) '&' textToPrt(941:end)];
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% Panel B: Number of stocks and market capitalization of portfolios
a = Results.Tab_CondSizeSort.PanelB.a;
h = Results.Tab_CondSizeSort.PanelB.h;

fprintf(fid, ['\\multicolumn{13}{l}{Panel B: Portfolio average number of firms and market capitalization}\\\\[2pt]' '\n']);
fprintf(fid, ['& & \\multicolumn{5}{c}{', Results.Text.signalChar, ' Quintiles} & & \\multicolumn{5}{c}{', Results.Text.signalChar, ' Quintiles} \\\\[2pt]' '\n']);
fprintf(fid, ['& & \\multicolumn{5}{c}{Average $n$} & & \\multicolumn{5}{c}{Average market capitalization ($\\$10^6$)} \\\\[2pt]' '\n']);
fprintf(fid, ['& & (L) & (2) & (3) & (4) & (H) & &(L) & (2) & (3) & (4) & (H) \\\\\\cline{3-7}\\cline{9-13}' '\n']);
fprintf(fid, ['\\parbox[t]{2mm}{\\multirow{5}{*}{\\rotatebox[origin=c]{90}{Size quintiles }}} ' '\n']);
textToPrt = replace(evalc('mat2Tex(a,a,h,0);'),'\',{'\\'});
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% End of Table 3
fprintf(fid, ['\\end{tabularx}' '\n']);
fprintf(fid, ['\\end{table}' '\n']);
fprintf(fid, ['\\end{landscape}' '\n\n\n']);
