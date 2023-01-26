function printEndOfPaperText(fid)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the text at end of the paper. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printEndOfPaperText(fid, Results)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - fid - file ID for writing
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printEndOfPaperText(fid, Results)
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

% 5. Bibliography
fprintf(fid, ['\\newpage' '\n']);
fprintf(fid, ['\\clearpage' '\n\n']);
fprintf(fid, ['\\bibliographystyle{apalike}' '\n']);
fprintf(fid, ['\\bibliography{newSignalTestBib}' '\n']);

% End of document
fprintf(fid, ['\\end{document}' '\n']);
fclose(fid);
