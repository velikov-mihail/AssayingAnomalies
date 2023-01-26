function getFFDailyFactors(Params)
% PURPOSE: This function downloads and stores the Fama-French daily 
% factors (dmkt, drf, dsmb, dhml, dcma, drmw, dumd)
%------------------------------------------------------------------------------------------
% USAGE:   
% getFFDailyFactors(Params)             
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
% getFFDailyFactors(Params)             
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Store the directories
dataDirPath = [Params.directory,'Data/'];
ffDirPath = [Params.directory,'Data/FF/'];

% Check if FF directory exists, make it if not
if ~exist(ffDirPath, 'dir')
    mkdir(ffDirPath)
end
addpath(genpath(ffDirPath));

% Load the dates
load ddates

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF3 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Unzip the FF 3-factor CSV file from the web
fileURL = 'http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip';
ff3FileName = unzip(fileURL,ffDirPath);

% Read in the 3 factors
opts = detectImportOptions(char(ff3FileName));
FF3factors = readtable(char(ff3FileName), opts);
FF3factors.Properties.VariableNames = {'dates','MKT','SMB','HML','RF'};

% Clean up the file - if it has any NaNs at the end
e = find(isnan(FF3factors.dates),1,'first');
FF3factors(e:end,:) = [];

% Save the  FF dates
dffdates = ddates;

% Intersect our dates with the ones from the Ken French webiste
[~, ia, ib] = intersect(ddates, FF3factors.dates);

% Store them
dmkt = nan(size(ddates));
dsmb = nan(size(ddates));
dhml = nan(size(ddates));
drf  = nan(size(ddates));

dmkt(ia) = FF3factors.MKT(ib)/100;
dsmb(ia) = FF3factors.SMB(ib)/100;
dhml(ia) = FF3factors.HML(ib)/100;
drf(ia)  = FF3factors.RF(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% UMD factor %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Unzip the FF daily UMD CSV file from the web
fileURL = 'http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip';
ffUMDFileName = unzip(fileURL, ffDirPath);

% Read daily UMD
opts = detectImportOptions(char(ffUMDFileName));
UMDFactor = readtable(char(ffUMDFileName), opts);
UMDFactor.Properties.VariableNames = {'dates','UMD'};

% Clean up the file - if it has any NaNs at the end
e = find(isnan(UMDFactor.dates), 1, 'first');
UMDFactor(e:end,:) = [];

% Intersect our dates with the ones from the Ken French webiste
[~,ia,ib]=intersect(ddates,UMDFactor.dates);

% Store daily UMD factor
dumd = nan(size(ddates));
dumd(ia) = UMDFactor.UMD(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF5 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Unzip the FF 5-factor CSV file from the web
fileURL = 'http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip';
ff5FileName=unzip(fileURL, ffDirPath);

% Read in the 5 factors
opts = detectImportOptions(char(ff5FileName));
FF5factors = readtable(char(ff5FileName), opts);
FF5factors.Properties.VariableNames = {'dates','MKT','SMB','HML','RMW','CMA','RF'};

% Clean up the file - it also includes annual returns for the factors;
e = find(isnan(FF5factors.dates), 1, 'first');
FF5factors(e:end,:) = [];

% Intersect our dates with the ones from the Ken French webiste
[~, ia, ib] =intersect(ddates, FF5factors.dates);

% Store the additional daily factors
dsmb2 = nan(size(ddates));
drmw  = nan(size(ddates));
dcma  = nan(size(ddates));

dsmb2(ia) = FF5factors.SMB(ib)/100;
drmw(ia)  = FF5factors.RMW(ib)/100;
dcma(ia)  = FF5factors.CMA(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%% Save the factors  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Creat a few useful matrices first 
const = .01*ones(size(drf));
dff3 = [const dmkt dsmb dhml];
dff4 = [dff3 dumd];
dff5 = [const dmkt dsmb2 dhml drmw dcma];
dff6 = [dff5 dumd];

% Save them in dff.mat
save([dataDirPath,'dff.mat'], 'dffdates', 'const', 'drf', 'dmkt', 'dsmb', 'dsmb2', 'dhml', 'dumd', 'drmw', 'dcma', 'dff3', 'dff4', 'dff5', 'dff6');

% Timekeeping
fprintf('Daily Fama-French factors creation complete @ %s.\n',char(datetime('now')));
