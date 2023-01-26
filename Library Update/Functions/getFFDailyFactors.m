function getFFDailyFactors(Params)
% PURPOSE: 
% turnover
%---------------------------------------------------
% USAGE:   getFFDailyFactors(Params);      
%---------------------------------------------------
% Inputs:
% Output:

dataDirPath=[Params.directory,'Data/'];
ffDirPath=[Params.directory,'Data/FF/'];

if ~exist(ffDirPath, 'dir')
    mkdir(ffDirPath)
end


addpath(genpath(Params.directory));

load ddates

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF3 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 3-factor CSV file from the web
ff3FileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip',ffDirPath);

% Read in the 3 factors
opts=detectImportOptions(char(ff3FileName));
FF3factors=readtable(char(ff3FileName),opts);
FF3factors.Properties.VariableNames={'dates','MKT','SMB','HML','RF'};

% Clean up the file - if it has any NaNs at the end
e=find(isnan(FF3factors.dates),1,'first');
FF3factors(e:end,:)=[];

% Save the factors
dffdates = ddates;

% Intersect our dates with the ones from the Ken French webiste
[~,ia,ib] =intersect(ddates,FF3factors.dates);

dmkt = nan(size(ddates));
dsmb = nan(size(ddates));
dhml = nan(size(ddates));
drf = nan(size(ddates));

dmkt(ia)=FF3factors.MKT(ib)/100;
dsmb(ia)=FF3factors.SMB(ib)/100;
dhml(ia)=FF3factors.HML(ib)/100;
drf(ia)=FF3factors.RF(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% UMD factor %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 3-factor CSV file from the web
ffUMDFileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip',ffDirPath);

opts=detectImportOptions(char(ffUMDFileName));
UMDFactor=readtable(char(ffUMDFileName),opts);
UMDFactor.Properties.VariableNames={'dates','UMD'};


% Clean up the file - if it has any NaNs at the end
e=find(isnan(UMDFactor.dates),1,'first');
UMDFactor(e:end,:)=[];

% Intersect our dates with the ones from the Ken French webiste
[~,ia,ib]=intersect(ddates,UMDFactor.dates);

dumd = nan(size(ddates));

dumd(ia)=UMDFactor.UMD(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%% FF5 factors %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Unzip the FF 5-factor CSV file from the web
ff5FileName=unzip('http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip',ffDirPath);

% Read in the 5 factors
opts=detectImportOptions(char(ff5FileName));
FF5factors=readtable(char(ff5FileName),opts);
FF5factors.Properties.VariableNames={'dates','MKT','SMB','HML','RMW','CMA','RF'};

% Clean up the file - if it has any NaNs at the end
e=find(isnan(FF5factors.dates),1,'first');
FF5factors(e:end,:)=[];

[~,ia,ib] =intersect(ddates,FF5factors.dates);

dsmb2 = nan(size(ddates));
drmw = nan(size(ddates));
dcma = nan(size(ddates));

dsmb2(ia)=FF5factors.SMB(ib)/100;
drmw(ia)=FF5factors.RMW(ib)/100;
dcma(ia)=FF5factors.CMA(ib)/100;

%%%%%%%%%%%%%%%%%%%%%%%%%% Save the factors  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


const = .01*ones(size(drf));
dff3 = [const dmkt dsmb dhml];
dff4 = [dff3 dumd];
dff5 = [const dmkt dsmb2 dhml drmw dcma];
dff6 = [dff5 dumd];

save([dataDirPath,'dff.mat'], 'dffdates', 'const', 'drf', 'dmkt', 'dsmb', 'dsmb2', 'dhml', 'dumd', 'drmw', 'dcma', 'dff3', 'dff4', 'dff5', 'dff6');

