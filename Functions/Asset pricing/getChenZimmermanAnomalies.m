function [anoms,labels,anomaly_summary]=getChenZimmermanAnomalies()
% PURPOSE: This function runs a univariate sort and calculates portfolio
% average returns and estimates alphas and loadings on a factor model
%------------------------------------------------------------------------------------------
% USAGE:   
% [anoms,labels,anomaly_summary]=getChenZimmermanAnomalies()                                            
%------------------------------------------------------------------------------------------
% Required Inputs:
%------------------------------------------------------------------------------------------
% Output:
%        -anoms - a 3-d numeric array corredsponding to (nmonths x nstocks x nanoms)
%        -labels - a vector of Acronyms for each anomaly
%        -anomaly_summary - a table with documentation for anomalies (publication dates, 
%                           sample periods, etc.)
%------------------------------------------------------------------------------------------
% Examples:
%
% [anoms,labels,anomaly_summary]=getChenZimmermanAnomalies();                                     
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses getAnomalySignals(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.
% The function requires that you have downloaded the following two files
% from Andrew Chen and Tom Zimmerman's open-source asset pricing library:
% https://drive.google.com/file/d/1-1RUq2wUADu_ncvQJCYY3wxDhqhHxBow/view
% https://docs.google.com/spreadsheets/d/18DvZPscKsD0_ZeeUMjyXhF1qn0emDVaj/edit#gid=70837236
% Try to code this in using: http://blog.vadimfrolov.com/download-a-file-from-google-drive-programmatically/

% Check if the two files were downloaded
if ~exist('signed_predictors_dl_wide.csv','file') || ~exist('SignalDocumentation.xlsx','file')
    error('Chen-Zimmerman files not on path. Please, download files from https://www.openassetpricing.com/.');
end

% Read in the anomaly signals. This requires over ~100GB of RAM if your data goes back to 1925
[anoms, labels]=getAnomalySignals('signed_predictors_dl_wide.csv','permno','yyyymm');
fprintf('Done getting signals at at %s.\n',char(datetime('now')));

% % Alternatively, you can download 1 at a time and store them
% opts=detectImportOptions('signed_predictors_dl_wide.csv');
% anomNames=opts.VariableNames(~ismember(opts.VariableNames,{'permno','yyyymm'}))';
% for i=1:length(anomNames)    
%     thisLabel=anomNames(i);
%     tic;
%     [thisAnom, ~]=getAnomalySignals('signed_predictors_dl_wide.csv','permno','yyyymm','Name',thisLabel);
%     toc;
%     tempStruct.(char(thisLabel))=thisAnom;
%     save(['Data/Anomalies/',char(thisLabel),'.mat'],'-struct','tempStruct',char(thisLabel));
% end
    


% WRDS doesn't let CZ share these three anomalies, so we need to add them
numanoms=size(anoms,3);
load prc
load ret
load me
anoms(:,:,numanoms+1)=-abs(prc);
anoms(:,:,numanoms+2)=-ret;
anoms(:,:,numanoms+3)=-me;
labels(numanoms+1)={'Price'};
labels(numanoms+2)={'STreversal'};
labels(numanoms+3)={'Size'};

% Read in the anomaly documentation into a table called anomaly_summary
opts=detectImportOptions('SignalDocumentation.xlsx','Sheet','BasicInfo');
data=readtable('SignalDocumentation.xlsx',opts);
anomaly_summary=data(ismember(data.Cat_Signal,{'Predictor'}),:);
opts=detectImportOptions('SignalDocumentation.xlsx','Sheet','AddInfo');
data=readtable('SignalDocumentation.xlsx',opts);
opts.VariableTypes(strcmp(opts.VariableNames,'LSQuantile'))={'double'};
data=data(ismember(data.Cat_SignalFormula,{'Predictor'}),:);
data=data(:,{'Acronym','StockWeight','LSQuantile','PortfolioPeriod','StartMonth','Filter','QuantileFilter'});
anomaly_summary=outerjoin(anomaly_summary,data,'MergeKeys',1,'Type','Left');
anomaly_summary.LSQuantile=str2double(anomaly_summary.LSQuantile);

% Sort them to be in the same order
[labels, I]=sort(labels);
anoms=anoms(:,:,I);

[~,I]=sort(anomaly_summary.Acronym);
anomaly_summary=anomaly_summary(I,:);
