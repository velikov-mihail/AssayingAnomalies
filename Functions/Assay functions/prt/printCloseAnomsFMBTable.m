function printCloseAnomsFMBTable(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the Fama-MacBeth with close anomalies table. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCloseAnomsFMBTable(fid, Results)
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
% printCloseAnomsFMBTable(fid, Results)
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
nCloseChar = num2words(Results.Text.nCloseAnoms);
closeAnoms = Results.Text.closeAnoms;

% Table 4 - Fama-MacBeth controlling for close related anomalies
fprintf(fid, ['\\begin{table}[!htbp]' '\n']);
fprintf(fid, ['\\small' '\n']);
fprintf(fid, ['\\caption{Fama-MacBeths controlling for most closely related anomalies\\\\' '\n']);
fprintf(fid, ['\\small{This table presents Fama-MacBeth results of returns on ', Results.Text.signalChar, '. ', ... 
              'and the ', nCloseChar, ' most closely related anomalies. The regressions take the following form: ', ...
              '$r_{i,t}=\\alpha+\\beta_{', Results.Text.signalChar, '} ',Results.Text.signalChar, ...
              '_{i,t}+\\sum_{k=1}^', nCloseChar, ' \\beta_{X_k} X_{i,t}^k+\\epsilon_{i,t}$. ', ...
              'The ', nCloseChar, ' most closely related anomalies, $X$, are ', closeAnoms, '. ', ...
              'These anomalies were picked as those with the ',...
              'lowest absolute sum of t-statistics across the three Panels in Figure~\\ref{fig:conditionalStrategies}. ',...
              'The sample period is ', char(num2str(Results.Text.timePeriod(1))), ...
              ' to ', char(num2str(Results.Text.timePeriod(2))), '.}}' '\n']);
fprintf(fid, ['\\label{tab:closeAnomFMB}' '\n']);
fprintf(fid, ['\\begin{tabularx}{\\linewidth}{l*9{>{\\centering\\arraybackslash}X}}\\hline' '\n']);

% Panel A: Averge returns and strategy results
a = Results.Tab_CloseFMB.a;
tA = Results.Tab_CloseFMB.tA;
h = Results.Tab_CloseFMB.h;
textToPrt = replace(evalc('mat2Tex(a,tA,h,2);'),'\',{'\\'});
fprintf(fid,textToPrt);
fprintf(fid, ['\\hline' '\n']);

% End of Table 4
fprintf(fid, ['\\end{tabularx}' '\n']);
fprintf(fid, ['\\end{table}' '\n']);
