function setupWRDSConn(Params)
% PURPOSE: This function creates the WRDS PostgreSQL JDBC connection
%------------------------------------------------------------------------------------------
% USAGE:   
% setupWRDSConn(Params)              % Creates the WRDS PostgreSQL JDBC connection                                 
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
% setupWRDSConn(Params)              
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


% Timekeeping
fprintf('\n\n\nSetting up WRDS connection. Setup started at %s.\n', char(datetime('now')));

% Find the JDBC driver location. Search for it on the path
driverLocationDir = (dir(fullfile(Params.directory,'**/postgresql*.jar')));
if isempty(driverLocationDir)
    % if it's not on the path, ask the user to select it
    [file, path] = uigetfile('*.jar', ...                                
         'Please select PostgreSQL JDBC driver location:'); 
    driverLocation = [path, file];
else
    driverLocation = [strrep(driverLocationDir.folder,'\','/'), '/', driverLocationDir.name];
end    

% Set up the options for the WRDS connection. It uses PostgreSQL and
% requires a JDBC postgreSQL driver in the corresponding location in Params
opts = configureJDBCDataSource('Vendor', 'PostgreSQL');
opts = setConnectionOptions(opts, 'DataSourceName', 'WRDS', ...
                                  'DatabaseName', 'wrds', ...
                                  'Server', 'wrds-pgdata.wharton.upenn.edu', ...
                                  'PortNumber', 9737, ...
                                  'JDBCDriverLocation', driverLocation);

% Test the status of the connection
status = testConnection(opts,Params.username,Params.pass);
if status == 1
    fprintf('Connection to WRDS is successful.\n');
else 
    error('\nConnection to WRDS unsuccessful. Check JAVA driver installation.\n');
end

% Save it so that we can only call it by its name, 'WRDS'
saveAsJDBCDataSource(opts)

% Timekeeping
fprintf('WRDS connection setup ended at %s.\n', char(datetime('now')));
