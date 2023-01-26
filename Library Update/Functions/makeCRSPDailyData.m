function makeCRSPDailyData(Params)
% PURPOSE: This function uses the stored required tables from the CRSP
% daily files to create matrices of dimensions number of days by number
% of stocks for all variables downloaded from the daily CRSP file
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCRSPDailyData(Params)              % Turns the CRSP daily file into matrices
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
% makeCRSPDailyData(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making variables from daily CRSP. Let''s read the files in first. Run started at %s.\n', char(datetime('now')));

% Store the daily CRSP data path
dailyCRSPPath = [Params.directory, 'Data/CRSP/daily/'];

% Store the daily CRSP directory contents and number of files
dailyCrspFiles = dir([Params.directory, '/Data/CRSP/daily/crsp_dsf*.csv']);
nFiles = length(dailyCrspFiles);

% Initiate the crsp_dsf table
crsp_dsf=[];

% Loop through the files
for i=1:nFiles
    % Read in the current file
    opts = detectImportOptions(dailyCrspFiles(i).name);
    temp_dsf = readtable(dailyCrspFiles(i).name, opts);
    crsp_dsf=[crsp_dsf; temp_dsf];
end

% Keep only the relevant permnos
load permno
idxToDrop = ~ismember(crsp_dsf.permno,permno);
crsp_dsf(idxToDrop,:) = [];

% Create ddates in YYYYMMDD format
crsp_dsf.ddates = 10000 * year(crsp_dsf.date) + ...
                    100 * month(crsp_dsf.date) + ...
                          day(crsp_dsf.date);    
ddates = unique(crsp_dsf.ddates);
 
% Store the number of days and number of stocks
nDays = length(ddates);
nStocks = length(permno);

% Initialize the variables
dret_x_dl = nan(nDays, nStocks);
dask      = nan(nDays, nStocks);
daskhi    = nan(nDays, nStocks);
dbid      = nan(nDays, nStocks);
dbidlo    = nan(nDays, nStocks);
dshrout   = nan(nDays, nStocks);
dvol      = nan(nDays, nStocks);
dprc      = nan(nDays, nStocks);
dopen     = nan(nDays, nStocks);
dnumtrd   = nan(nDays, nStocks);
dcfacshr  = nan(nDays, nStocks);
dcfacpr   = nan(nDays, nStocks);

fprintf('\n\n\nNow working on assigning the data to our familiar daily matrices. Run started at %s. This step takes a couple of hours.\n', char(datetime('now')));

% Loop through all firms and find the relevant dates, assign to the
% corresponding matrices
for c = 1:nStocks
    % Find the observations for this permno in crsp_dsf
    thisStockInd = find(crsp_dsf.permno==permno(c));
    
    % Intersect the dates 
    [~, rowIndex, tempIndex] = intersect(ddates, crsp_dsf.ddates(thisStockInd));
    
    % Find the index in the table
    indInTable = thisStockInd(tempIndex);
    
    % Assign the variables
    dret_x_dl(rowIndex, c) = crsp_dsf.ret(indInTable);
    dask(rowIndex, c)      = crsp_dsf.ask(indInTable);
    daskhi(rowIndex, c)    = crsp_dsf.askhi(indInTable);
    dbid(rowIndex, c)      = crsp_dsf.bid(indInTable);
    dbidlo(rowIndex, c)    = crsp_dsf.bidlo(indInTable);
    dshrout(rowIndex, c)   = crsp_dsf.shrout(indInTable);
    dvol(rowIndex, c)      = crsp_dsf.vol(indInTable);
    dprc(rowIndex, c)      = crsp_dsf.prc(indInTable);
    dopen(rowIndex, c)     = crsp_dsf.openprc(indInTable);
    dnumtrd(rowIndex, c)   = crsp_dsf.numtrd(indInTable);
    dcfacshr(rowIndex, c)  = crsp_dsf.cfacshr(indInTable);
    dcfacpr(rowIndex, c)   = crsp_dsf.cfacpr(indInTable);
end

% Timekeeping
fprintf('CRSP daily variables assigned at %s. Now storing them.\n', char(datetime('now')));

% Store all the variables
save([dailyCRSPPath,'dprc.mat'], 'dprc', '-v7.3');
save([dailyCRSPPath,'dvol.mat'], 'dvol', '-v7.3');
save([dailyCRSPPath,'dbid.mat'], 'dbid', '-v7.3');
save([dailyCRSPPath,'dask.mat'], 'dask', '-v7.3');
save([dailyCRSPPath,'dbidlo.mat'], 'dbidlo', '-v7.3');
save([dailyCRSPPath,'daskhi.mat'], 'daskhi', '-v7.3');
save([dailyCRSPPath,'dopen.mat'], 'dopen', '-v7.3');
save([dailyCRSPPath,'dshrout.mat'], 'dshrout', '-v7.3');
save([dailyCRSPPath,'dret_x_dl.mat'], 'dret_x_dl', '-v7.3');
save([dailyCRSPPath,'dnumtrd.mat'], 'dnumtrd', '-v7.3');
save([dailyCRSPPath,'dcfacshr.mat'], 'dcfacshr', '-v7.3');
save([dailyCRSPPath,'dcfacpr.mat'], 'dcfacpr', '-v7.3');

% Create the end of month flag and store ddates
eomflag = floor(ddates/100) ~= lead(floor(ddates/100),1,1);
save([dailyCRSPPath,'ddates.mat'], 'ddates', 'eomflag');

% Timekeeping
fprintf('CRSP daily variables run ended at %s.\n', char(datetime('now')));
