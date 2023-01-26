function getWRDSTable(WRDS,libname,memname,subdir,varargin)
% PURPOSE: This function downloads and stores the required tables from the CRSP monthly file
%------------------------------------------------------------------------------------------
% USAGE:   
% getWRDSTable(WRDS,libname,memname,subdir)                         % Downloads and stores the the selected table from WRDS in the chosen subdirectory
% getWRDSTable(WRDS,libname,memname,subdir,Name,Value)              % Adds an optional argument that indicates to execute a specific query
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -WRDS - a database connection to be used for downloading data from  WRDS directly
%        -libname - WRDS library name (e.g., CRSP)
%        -memname - WRDS table name (e.g., MSF)
%        -subdir - WRDS table name (e.g., MSF)
% Optional Name-Value Pair Arguments:
%        -'customQuery' - a custom SQL query to execute on the WRDS server
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% getWRDSTable(WRDS,CRSP,MSF,[Params.directory,'Data/CRSP/']) % Downloads the CRSP monthly stock file (MSF) table from WRDS and stores it as CRSP_MSF.csv in the selected directory
% getWRDSTable(WRDS,CRSP,MSF,[Params.directory,'Data/CRSP/'], % Downloads and stores the selected query from WRDS and stores it as CRSP_MSF.csv in the selected directory
%              ...'customQuery', ['select permno, ret, date from CRSP.MSF']) 
% getWRDSTable(WRDS,'COMP','FUNDA',compustatDirPath,'customQuery',COMPUSTATAnnualQuery);
% getWRDSTable(WRDS,'COMP','FUNDQ',compustatDirPath,'customQuery',COMPUSTATQuarterlyQuery);
%------------------------------------------------------------------------------------------
% Dependencies:
%       None
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


p = inputParser;
validConn = @(x) isopen(x);
validChar = @(x) ischar(x);
addRequired(p,'WRDS',validConn);
addRequired(p,'libname',validChar);
addRequired(p,'memname',validChar);
addRequired(p,'subdir',validChar);
addParameter(p,'customQuery','N/A',validChar);
parse(p,WRDS,libname,memname,subdir,varargin{:});


WRDS = p.Results.WRDS;
libname = p.Results.libname;
memname = p.Results.memname;
subdir = p.Results.subdir;
customQuery = p.Results.customQuery;

tableName = [libname,'.',memname];

if strcmp(customQuery,'N/A') 
    % Check size of the wrds table
    wrdsTableRowCount = fetch(WRDS,['select count(*) from ',tableName]);
    if wrdsTableRowCount.count == 0
        error([tableName,' has 0 rows. Connection problem or wrong table name.']);
    end
else
    wrdsTableRowCount=table(0,'VariableNames',{'count'});
end

% Download the WRDS table
fprintf('Downloading the WRDS table %s. Download started at %s.\n',tableName,char(datetime('now')));
if strcmp(customQuery,'N/A') 
    wrdsTable = fetch(WRDS,['select * from ',tableName]);
else
    wrdsTable = fetch(WRDS,customQuery);
end

if height(wrdsTable) ~= wrdsTableRowCount.count && strcmp(customQuery,'N/A') % Check if the entire table was downloaded. Sometimes internet issues and/or JDBC issues prevent that from happening
    error(['Error: ',tableName,' was not fully downloaded']);
else
    fprintf('%s download ended at %s.\n',tableName,char(datetime('now')));
    fprintf('%s has %d rows and %d columns.\n',tableName,size(wrdsTable,1),size(wrdsTable,2));
end

% Store the raw WRDS table into a .csv file
fprintf('Now exporting the WRDS table %s into .csv. Export started at %s.\n',tableName,char(datetime('now')));
writetable(wrdsTable,[subdir,libname,'_',memname,'.csv']);
fprintf('%s export ended at %s.\n',tableName,char(datetime('now')));
