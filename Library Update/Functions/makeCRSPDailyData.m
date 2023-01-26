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
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

fprintf('\n\n\nNow working on making variables from daily CRSP. Let''s read the files in first. Run started at %s.\n',char(datetime('now')));

dailyCrspFiles=dir([Params.directory,'/Data/CRSP/daily/CRSP_DSF*.csv']);

crsp_dsf=[];

for i=1:length(dailyCrspFiles)
    opts=detectImportOptions(dailyCrspFiles(i).name);
    temp_csv=readtable(dailyCrspFiles(i).name,opts);
    crsp_dsf=[crsp_dsf; temp_csv];
end

% Keep only the relevant permnos
load permno
crsp_dsf(~ismember(crsp_dsf.permno,permno),:)=[];

% Create ddates in YYYYMMDD format
crsp_dsf.ddates=10000*year(crsp_dsf.date)+100*month(crsp_dsf.date)+day(crsp_dsf.date);    
ddates=unique(crsp_dsf.ddates);
 
% Initialize the variables
dret=nan(length(ddates),length(permno));
dask=nan(length(ddates),length(permno));
daskhi=nan(length(ddates),length(permno));
dbid=nan(length(ddates),length(permno));
dbidlo=nan(length(ddates),length(permno));
dshrout=nan(length(ddates),length(permno));
dvol=nan(length(ddates),length(permno));
dprc=nan(length(ddates),length(permno));
dopen=nan(length(ddates),length(permno));
dnumtrd=nan(length(ddates),length(permno));
dcfacshr=nan(length(ddates),length(permno));
dcfacpr=nan(length(ddates),length(permno));

fprintf('\n\n\nNow working on assigning the data to our familiar daily matrices. Run started at %s. This step takes a couple of hours.\n',char(datetime('now')));

% Loop through all firms and find the relevant dates, assign to the
% corresponding matrices
for c=1:length(permno)
    ind=find(crsp_dsf.permno==permno(c));
    [~,rowIndex,tempIndex] = intersect(ddates,crsp_dsf.ddates(ind));
    dret(rowIndex,c)=crsp_dsf.ret(ind(tempIndex));
    dask(rowIndex,c)=crsp_dsf.ask(ind(tempIndex));
    daskhi(rowIndex,c)=crsp_dsf.askhi(ind(tempIndex));
    dbid(rowIndex,c)=crsp_dsf.bid(ind(tempIndex));
    dbidlo(rowIndex,c)=crsp_dsf.bidlo(ind(tempIndex));
    dshrout(rowIndex,c)=crsp_dsf.shrout(ind(tempIndex));
    dvol(rowIndex,c)=crsp_dsf.vol(ind(tempIndex));
    dprc(rowIndex,c)=crsp_dsf.prc(ind(tempIndex));
    dopen(rowIndex,c)=crsp_dsf.openprc(ind(tempIndex));
    dnumtrd(rowIndex,c)=crsp_dsf.numtrd(ind(tempIndex));
    dcfacshr(rowIndex,c)=crsp_dsf.cfacshr(ind(tempIndex));
    dcfacpr(rowIndex,c)=crsp_dsf.cfacpr(ind(tempIndex));
end

fprintf('CRSP daily variables assigned at %s. Now storing them.\n', char(datetime('now')));

save -v7.3 Data/CRSP/daily/dprc dprc
save -v7.3 Data/CRSP/daily/dvol dvol
save -v7.3 Data/CRSP/daily/dbid dbid
save -v7.3 Data/CRSP/daily/dask dask
save -v7.3 Data/CRSP/daily/dbidlo dbidlo
save -v7.3 Data/CRSP/daily/daskhi daskhi
save -v7.3 Data/CRSP/daily/dopen dopen
save -v7.3 Data/CRSP/daily/dshrout dshrout
save -v7.3 Data/CRSP/daily/dret_x_dl dret
save -v7.3 Data/CRSP/daily/dnumtrd dnumtrd
save -v7.3 Data/CRSP/daily/dcfacshr dcfacshr
save -v7.3 Data/CRSP/daily/dcfacpr dcfacpr
eomflag = floor(ddates/100) < floor([ddates(2:end);ddates(end)+100]/100); % end of month flag
save Data/CRSP/daily/ddates ddates eomflag

fprintf('CRSP daily variables run ended at %s.\n', char(datetime('now')));
