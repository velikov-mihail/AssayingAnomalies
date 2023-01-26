function WRDS=callWRDSConnection(username,pass)
% PURPOSE: This function calls the WRDS connection (need to be set-up)
%------------------------------------------------------------------------------------------
% USAGE:   
% WRDS=callWRDSConnection(username,pass)              % Calls the WRDS connection (need to be set-up)                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -username - WRDS username
%        -pass - WRDS password 
%------------------------------------------------------------------------------------------
% Output:
%        -WRDS - a database connection to be used for downloading data from  WRDS directly
%------------------------------------------------------------------------------------------
% Examples:
%
% WRDS=callWRDSConnection(username,pass)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires setupWRDSConn() to be run first
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Pass the connection object as an output
WRDS = database('WRDS', username, pass, 'ErrorHandling', 'Report');