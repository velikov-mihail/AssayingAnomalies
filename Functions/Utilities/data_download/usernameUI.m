function userName = usernameUI()
% PURPOSE: This function asks the user to input their WRDS username
%------------------------------------------------------------------------------------------
% USAGE:   
% userMame = usernameUI()                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -None
%------------------------------------------------------------------------------------------
% Output:
%        -userName - a character array of the input username
%------------------------------------------------------------------------------------------
% Examples:
%
% Params.username = usernameUI()              
%------------------------------------------------------------------------------------------
% Dependencies:
%       None
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

opts.Resize='on';
opts.WindowStyle='normal';
userName = char(inputdlg('','Enter your WRDS username:',[1 82],{''},opts));