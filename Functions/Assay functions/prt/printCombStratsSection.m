function printCombStratsSection(fid, Results)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the the Combination strategy section in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCombStratsSection(fid, Results)
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
% printCombStratsSection(fid, Results)
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


nAnoms = Results.Text.nAnoms;
signalChar = Results.Text.signalChar;
numCombinationMethods = length(Results.Fig_CombStrat.ttl);
numCombMethodChar = num2words(numCombinationMethods);

fprintf(fid, ['\\section{Does ', signalChar, ' add relative to the whole zoo?} \n']);
fprintf(fid, ['\\label{sec:combStrat}' '\n\n\n']);


pretWithout = Results.Fig_CombStrat.yWithout;
pretWithout(isnan(pretWithout)) = 0;     
cumPretWithout = cumprod(1+pretWithout);   

pretWith = Results.Fig_CombStrat.yWith;
pretWith(isnan(pretWith)) = 0; 
cumPretWith = cumprod(1+pretWith);   

Alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

section_6_text = [ ...
    'Finally, we can ask how much adding ', signalChar, ' to the entire factor zoo could ', ...
    'improve investment performance. Figure~\\ref{fig:combStrat} plots the growth of ', ...
    '\\$1 invested in trading strategies ', ...
    'that combine multiple anomalies following \\citet{ChenVelikov2022}. The combinations ', ...
    'use either the ', nAnoms, ' anomalies from the zoo that satisfy our inclusion criteria ', ...
    ' (blue lines) or these ', nAnoms, ' anomalies augmented with the ', signalChar, ' signal. ', ...
    'We consider ', numCombMethodChar, ' different methods for combining signals.\n\n' ];


for i = 1:numCombinationMethods
    endDollarWithout = sprintf('%.2f', cumPretWithout(end, i));
    endDollarWith = sprintf('%.2f', cumPretWith(end, i));
    thisMethodExplanation = char(Results.Fig_CombStrat.explanation(i));

    temp_text = ['Panel ', Alphabet(i), ' shows results using ``', char(Results.Fig_CombStrat.ttl(i)), ''''' ', ...
                 'as the combination method. ', thisMethodExplanation, ' For this method, ', ...
                 '\\$1 investment in the ', nAnoms, '-anomaly combination strategy ', ...
                 'grows to \\$', endDollarWithout, ', while \\$1 investment in the combination ', ...
                 'strategy that includes ', signalChar, ' grows to \\$', endDollarWith, '.\n\n'];
    section_6_text = [section_6_text temp_text];     
end

section_6_text = [section_6_text '\n\n\n'];
fprintf(fid, section_6_text);  

