function printCloseAnomsSpanTable(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the spanning tests with close anomalies table. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCloseAnomsSpanTable(fid, Results)
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
% printCloseAnomsSpanTable(fid, Results)
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

% Store some variables
nClose = Results.Text.nCloseAnoms;
nCloseChar = num2words(Results.Text.nCloseAnoms);
closeAnoms = Results.Text.closeAnoms;

% Table 5 - Spanning tests controlling for close related anomalies
fprintf(fid, ['\\begin{table}[!htbp]' '\n']);
fprintf(fid, ['\\small' '\n']);
fprintf(fid, ['\\caption{Spanning tests controlling for most closely related anomalies\\\\' '\n']);
fprintf(fid, ['\\small{This table presents spanning tests results of regressing returns to the ', ...
              Results.Text.signalChar, ' trading strategy on trading strategies exploiting ', ... 
              'the six most closely related anomalies. The regressions take the following form: ', ...
              '$r_{t}^{', Results.Text.signalChar, '}=\\alpha+ \\sum_{k=1}^', char(num2str(nClose)), ' \\beta_{X_k} r_{t}^{X_k}+\\sum_{j=1}^6 ', ...
              '\\beta_{f_j} r_t^{f_j}+\\epsilon_t$, where $X_k$ indicates each of the ', nCloseChar, ' most-closely related anomalies ', ...
              'and $f_j$ indicates the six factors from ', ...
              'the \\citet{FamaFrench2015} five-factor model augmented with the \\citet{Carhart1997} momentum factor. ', ...
              'The ', nCloseChar, ' most closely related anomalies, $X$, are ', closeAnoms, '. ', ...
              'These anomalies were picked as those with the ',...
              'lowest absolute sum of t-statistics across the three Panels in Figure~\\ref{fig:conditionalStrategies}. ',...
              'The sample period is ', char(num2str(Results.Text.timePeriod(1))), ...
              ' to ', char(num2str(Results.Text.timePeriod(2))), '.}}' '\n']);
fprintf(fid, ['\\label{tab:closeAnomSpan}' '\n']);
fprintf(fid, ['\\begin{tabularx}{\\linewidth}{l*9{>{\\centering\\arraybackslash}X}}\\hline' '\n']);
a = Results.Tab_CloseSpan.a;
tA = Results.Tab_CloseSpan.tA;
h = Results.Tab_CloseSpan.h;
textToPrt = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% End of Table 5
fprintf(fid, ['\\end{tabularx}' '\n']);
fprintf(fid, ['\\end{table}' '\n']);
