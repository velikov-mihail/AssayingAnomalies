function printDocumentHeader(fid)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It prints the header information in the latex file. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printDocumentHeader(fid)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - fid - file ID for writing
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printDocumentHeader(fid)
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


% Document header
fprintf(fid, ['\\documentclass[12pt]{article}' '\n']);
fprintf(fid, ['\\usepackage{amsfonts,amsmath,amssymb,amsthm,setspace,enumerate,graphicx,threeparttable,multirow,fullpage,comment,booktabs,array,tabularx,lscape,verbatim,titling,pdfpages,natbib,rotating,pdflscape,subcaption} ' '\n']);
fprintf(fid, ['\\usepackage[labelsep=colon,labelfont=bf,justification=justified,singlelinecheck=false]{caption}  ' '\n']);
fprintf(fid, ['\\usepackage[top=1in,bottom=1in]{geometry} ' '\n']);
fprintf(fid, ['\\usepackage[title]{appendix} ' '\n']);
fprintf(fid, ['\\usepackage[]{hyperref} ' '\n']);
fprintf(fid, ['\\usepackage{xcolor} ' '\n']);
fprintf(fid, ['\\hypersetup{colorlinks,linkcolor={blue!50!black},citecolor={blue!50!black},urlcolor={blue!80!black}} ' '\n']);

