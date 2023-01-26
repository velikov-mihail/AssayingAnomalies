function printTitlePage(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the the title page in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printTitlePage(fid, Results)
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
% printTitlePage(fid, Results, formEntries)
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

% Store the form entries
signalInfo = Results.signalInfo;

% Title
fprintf(fid, ['\\title{', 'Online Appendix for ', signalInfo.PaperTitle, ':\\\\\n',... 
                signalInfo.SignalName,' and the Cross Section of Stock Returns}' '\n']);

% Author
authorNames = strsplit(signalInfo.Authors, ' and ');
nAuthors = length(authorNames);
authorText = ['\\author{\\vspace{\\baselineskip}{', char(authorNames(1)), '}'];
if nAuthors > 1
    for i = 2:nAuthors
        authorText = [authorText, '\\and {', char(authorNames(i)), '}'];
    end
end
authorText = [authorText, '}'];
fprintf(fid, authorText);

% Date
fprintf(fid, ['\\date{\\today}' '\n']);

% Document begins
fprintf(fid, ['\\begin{document}' '\n\n']);

% Store some results for the abstract
nClose = Results.Text.nCloseAnoms;
nCloseChar = num2words(nClose);
grossFF6Alpha = sprintf('%2.0f', 100*Results.Tab_RobustSort.PanelA.a(1,6));
netFF6Alpha = sprintf('%2.0f', 100*Results.Tab_RobustSort.PanelB.a(1,6));
grossFF6Tstat = sprintf('%2.2f', Results.Tab_RobustSort.PanelA.tA(1,6));
netFF6Tstat = sprintf('%2.2f', Results.Tab_RobustSort.PanelB.tA(1,6));
alphaClose = sprintf('%2.0f', 100*Results.Tab_CloseSpan.a(1,end));
tstatClose = sprintf('%2.2f', Results.Tab_CloseSpan.tA(1,end));
closeAnoms = Results.Text.closeAnoms;

% Title page with space for abstract
fprintf(fid, ['\\maketitle' '\n']);
fprintf(fid, ['\\begin{abstract}' '\n\n']);
abstractText = ['This report studies the asset pricing implications of ', signalInfo.SignalName, ...
                ' (', signalInfo.SignalAcronym, '), and its robustness in predicting returns in the cross-section of equities ', ...
                'using the protocol proposed by \\citet{Novy-MarxVelikov2023}. ', ...
                'A value-weighted long/short trading strategy based on ', Results.Text.signalChar, ...
                ' achieves an annualized gross (net) Sharpe ratio of ', Results.Text.sharpeChar, ...
                ' (', Results.Text.netSharpeChar, '), and monthly average abnormal gross (net) ', ...
                'return relative to the \\citet{FamaFrench2015} five-factor model plus a momentum ', ...
                'factor of ', grossFF6Alpha, ' (', netFF6Alpha, ') bps/month with a t-statistic of ', ...
                grossFF6Tstat, ' (', netFF6Tstat, '), respectively. Its gross monthly alpha ', ...
                'relative to these six factors plus the ', nCloseChar, ' most closely related strategies from ', ...
                'the factor zoo (', closeAnoms, ') is ', alphaClose, ' bps/month with a ', ...
                't-statistic of ', tstatClose, '. \n'];
fprintf(fid, abstractText);                
fprintf(fid, ['\\end{abstract}' '\n\n']);
