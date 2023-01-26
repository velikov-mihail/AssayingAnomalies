function printIntroSection(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the the Introduction section in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printIntroSection(fid, Results)
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
% printIntroSection(fid, Results)
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

fprintf(fid, ['\\doublespacing', '\n\n']);
fprintf(fid, ['\\newpage' '\n']);
fprintf(fid, ['\\clearpage' '\n\n']);    
fprintf(fid, ['\\section{Introduction}' '\n']);
section_1_text = [ ...
    'The following automatically generated report tests the asset pricing implications of ', signalInfo.SignalName, ...
    ' (', signalInfo.SignalAcronym, '), and its robustness in predicting returns in the cross-section of equities. ', ...
    'It is produced using the methodology of \\citet{Novy-MarxVelikov2023}, from input data consisting of ', ...
    'firm-month observations for the proposed predictor.\\footnote{It used version v0.4.0 of the publicly available ', ...
    'code repository at \\href{https://github.com/velikov-mihail/AssayingAnomalies}', ...
    '{https://github.com/velikov-mihail/AssayingAnomalies}. See more details at ', ...
    '\\href{http://AssayingAnomalies.com}', ...
    '{http://AssayingAnomalies.com}.}' '\n\n\n'];
fprintf(fid, section_1_text);  
    
