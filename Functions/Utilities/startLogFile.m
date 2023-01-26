function startLogFile(directory, fileName)
% PURPOSE: This function creates a log file in the main directory
%------------------------------------------------------------------------------------------
% USAGE:   
% startLogFile(Params)              % Creates a log file in the main directory                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% startLogFile(Params)              
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

% Store the current date and time
currDateTime     = datetime('now');
currDateYYYYMMDD = num2str(10000 * year(currDateTime) + ...
                             100 * month(currDateTime) + ...
                                   day(currDateTime));

% Store the name of the log file and the current user
logFileName = regexprep([directory, ...
               '/', fileName,'_log_', ...
               char(currDateYYYYMMDD), ...
               '.txt'],'\','/');
currUser = getenv('USERNAME');

% Start the diary
diary(logFileName);

% Print out the start time
fprintf('Run of %s started on %s by user %s.\n', fileName, char(currDateTime), currUser);