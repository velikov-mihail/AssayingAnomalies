function getWRDSTable(WRDS,libname,memname,varargin)
% PURPOSE: This function downloads a custom WRDS table
%------------------------------------------------------------------------------------------
% USAGE:   
% getWRDSTable(WRDS,libname,memname)                         % Downloads and stores the the selected table from WRDS in the current folder
% getWRDSTable(WRDS,libname,memname,Name,Value)              % Adds an optional argument that indicates to execute a specific query
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -WRDS - a database connection to be used for downloading data from  WRDS directly
%        -libname - WRDS library name (e.g., CRSP)
%        -memname - WRDS table name (e.g., MSF)
% Optional Name-Value Pair Arguments:
%        -'dirPath' - directory, where the .csv file will be stored (current
%                  folder by default)
%        -'customQuery' - a custom SQL query to execute on the WRDS server
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% getWRDSTable(WRDS,'CRSP','MSF')                                          % Downloads the CRSP monthly stock file (MSF) table from WRDS and stores it as CRSP_MSF.csv in the current folder
% getWRDSTable(WRDS,'CRSP','MSF',[Params.directory,'Data/CRSP/'])          % Downloads the CRSP monthly stock file (MSF) table from WRDS and stores it as CRSP_MSF.csv in the selected directory
% getWRDSTable(WRDS,'CRSP','MSF',[Params.directory,'Data/CRSP/'],          % Downloads and stores the selected query from WRDS and stores it as CRSP_MSF.csv in the selected directory
%              ...'customQuery', ['select permno, ret, date from CRSP.MSF']) 
% getWRDSTable(WRDS,'COMP','FUNDA',compustatDirPath,'customQuery',COMPUSTATAnnualQuery);
% getWRDSTable(WRDS,'COMP','FUNDQ',compustatDirPath,'customQuery',COMPUSTATQuarterlyQuery);
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

% Parse the inputs 
p = inputParser;
validConn = @(x) isopen(x);
validChar = @(x) ischar(x);
validPath = @(x) ischar(x) && contains(x,{'/','\'});
addRequired(p, 'WRDS', validConn);
addRequired(p, 'libname', validChar);
addRequired(p, 'memname', validChar);
addOptional(p, 'dirPath', [regexprep(pwd, '\', '/'), '/'], validPath );
addOptional(p, 'customQuery', 'N/A', validChar);
parse(p, WRDS, libname, memname, varargin{:});

% Assign the inputs 
WRDS        = p.Results.WRDS;
libname     = p.Results.libname;
memname     = p.Results.memname;
dirPath     = p.Results.dirPath;
customQuery = p.Results.customQuery;

% Store the table name
tableName = [libname,'.',memname];

% If no custom query specified 
if strcmp(customQuery,'N/A') 
    % Check size of the wrds table
    wrdsTableRowCount = fetch(WRDS, ['select count(*) from ',tableName]);
    if wrdsTableRowCount.count == 0
        error([tableName,' has 0 rows. Connection problem or wrong table name.\n']);
    end
else
    wrdsTableRowCount = table(0,'VariableNames',{'count'});
end

% Download the WRDS table
fprintf('Downloading the WRDS table %s. Download started at %s.\n', tableName, char(datetime('now')));
if strcmp(customQuery,'N/A') 
    % Either the entire table
    wrdsTable = fetch(WRDS,['select * from ',tableName]);
else
    % Or the custom query
    wrdsTable = fetch(WRDS,customQuery);
end

% Check if the entire table was downloaded. Sometimes internet issues 
% and/or JDBC issues prevent that from happening.
if height(wrdsTable) ~= wrdsTableRowCount.count && strcmp(customQuery,'N/A') 
    error(['Error: ',tableName,' was not fully downloaded.\n']);
else
    fprintf('%s download ended at %s.\n', tableName, char(datetime('now')));
    fprintf('%s has %d rows and %d columns.\n', tableName, size(wrdsTable,1), size(wrdsTable,2));
end

% Store the raw WRDS table into a .csv file
fprintf('Now exporting the WRDS table %s into .csv. Export started at %s.\n', tableName, char(datetime('now')));
fileName = [dirPath,libname,'_',memname,'.csv'];
writetable(wrdsTable, fileName);
fprintf('%s export ended at %s.\n', tableName, char(datetime('now')));
