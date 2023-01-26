function getFFFactors(Params)
% PURPOSE: This function downloads and stores the Fama-French monthly factors (mkt,
% rf, smb, hml, cma, rmw, umd)
%------------------------------------------------------------------------------------------
% USAGE:   
% getFFFactors(Params)             
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
% getFFFactors(Params)             
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


dataDirPath=[Params.directory,'Data/'];
ffDirPath=[Params.directory,'Data/FF/'];

if ~exist(ffDirPath, 'dir')
    mkdir(ffDirPath)
end
addpath(genpath(Params.directory));

load dates

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF3 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 3-factor CSV file from the web
ff3FileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_data_Factors_CSV.zip',ffDirPath);

% Read in the 3 factors
opts=detectImportOptions(char(ff3FileName));
FF3factors=readtable(char(ff3FileName),opts);
FF3factors.Properties.VariableNames={'dates','MKT','SMB','HML','RF'};

% Clean up the file - it also includes annual returns for the factors;
e=find(isnan(FF3factors.dates),1,'first');
FF3factors(e:end,:)=[];

% Save the factors
ffdates = dates;

% Intersect our dates with the ones from the Ken French webiste
[~,ia,ib] =intersect(dates,FF3factors.dates);

% Store them
mkt = nan(size(dates));
smb = nan(size(dates));
hml = nan(size(dates));
rf = nan(size(dates));

mkt(ia)=FF3factors.MKT(ib)/100;
smb(ia)=FF3factors.SMB(ib)/100;
hml(ia)=FF3factors.HML(ib)/100;
rf(ia)=FF3factors.RF(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% UMD factor %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 3-factor CSV file from the web
ffUMDFileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip',ffDirPath);

% Read UMD
opts=detectImportOptions(char(ffUMDFileName));
UMDFactor=readtable(char(ffUMDFileName),opts);
UMDFactor.Properties.VariableNames={'dates','UMD'};


% Clean up the file - it also includes annual returns for the factors;
e=find(isnan(UMDFactor.dates),1,'first');
UMDFactor(e:end,:)=[];

% Intersect our dates with the ones from the Ken French webiste
[~,ia,ib]=intersect(dates,UMDFactor.dates);

% Store UMD factor
umd = nan(size(dates));
umd(ia)=UMDFactor.UMD(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF5 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 5-factor CSV file from the web
ff5FileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip',ffDirPath);

% Read in the 5 factors
opts=detectImportOptions(char(ff5FileName));
FF5factors=readtable(char(ff5FileName),opts);
FF5factors.Properties.VariableNames={'dates','MKT','SMB','HML','RMW','CMA','RF'};

% Clean up the file - it also includes annual returns for the factors;
e=find(isnan(FF5factors.dates),1,'first');
FF5factors(e:end,:)=[];


[~,ia,ib] =intersect(dates,FF5factors.dates);

smb2 = nan(size(dates));
rmw = nan(size(dates));
cma = nan(size(dates));

smb2(ia)=FF5factors.SMB(ib)/100;
rmw(ia)=FF5factors.RMW(ib)/100;
cma(ia)=FF5factors.CMA(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%% Save the factors  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


const = .01*ones(size(rf));
ff3 = [const mkt smb hml];
ff4 = [ff3 umd];
ff5 = [const mkt smb2 hml rmw cma];
ff6 = [ff5 umd];

save([dataDirPath,'ff.mat'], 'ffdates', 'const', 'rf', 'mkt', 'smb', 'smb2', 'hml', 'umd', 'rmw', 'cma', 'ff3', 'ff4', 'ff5', 'ff6');

fprintf('FFfactors creation complete.\n');