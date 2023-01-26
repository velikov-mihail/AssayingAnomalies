function output = fastbinsmooth(data,h,range,nxgrid,iker,kpar,imethod,endct)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%                                                                    %
%     Fast Binning method for calculating KERNEL DENSITY ESTIMATE,   %
%         Naraya-Watson KERNEL ESTIMATE,                             %
%       and local linear regression smoother                         %
%        ON AN EQUALLY SPACED GRID OF nxgrid POINTS,                 %
%         EQUALLY SPACED FROM left TO right                          %
%         h	IS THE BANDWIDTH, MUST BE A	SCALAR                       %
% Inputs:                                                            %
%          data: p x n matrix of the observed data.	                 %
%          density estimation: p = 1, regression p = 2.              %
%          h   : the bandwidth (must be a scalar)                    %
%         range: [left right] where                                  %
%         left: left bound of the interval on which the grid is set  %
%         right: left bound of the interval on which the grid is set %
%         nxgrid: number of grid points to compute the estimate      %
%         IKER = 1 - GAUSSIAN HIGHER ORDER FAMILY                    %
%                   KPAR = 1  -   STANDARD NORMAL                    %
%                   KPER = 2  -  GRAM CHARLIER, ORDER 4              %
%                   KPER = 3  -  GRAM CHARLIER,	ORDER 6	             %
%         IKER = 2 - BETA, SUPPORTED [-1,1], WITH                    %
%                   KPAR = 0  - UNIFORM                              %
%                   KPAR = 1 - EPANECHNIKOV                          %
%                   KPAR = 2  - BIWEIGHT                             %
%                   KPAR = 3  - TRIWEIGHT                            %
%           IMETHOD = the setting                                    %
%           IMETHOD = 0 -- NADARAYA WATSON ESTIMATOR                 %
%           IMETHOD = 1 -- LOCAL LINEAR REGRESSION ESTIMATOR         %
%           IMETHOD = 2 -- KERNEL DENSITY ESTIMATOR                  %
%          endct: = 0, truncating data beyond ends                   %
%                 = 1, counting data beyond ends                     %
% Outputs:                                                           %
%        output: the vector containing the height of the estimate    %
%       OUTPUT IS A VECTOR CONTAINING THE HEIGHT OF THE ESTIMATE     %
% Usage:                                                             %
%     Y = fastbinsmooth(data,h,range,nxgrid,iker,kpar,imethod,endct) %
% Defaults:                                                          %
%    IKER = 2;    BETA, SUPPORTED [-1,1]                             %
%    KPAR = 1;    EPANECHNIKOV                                       %
%    IMETHOD = 1; LOCAL LINEAR REGRESSION ESTIMATOR                  %
%    endct = 0;                                                      %
%    nxgrid=401                                                      %
% Uses: fest.mex                                                     %
%                                                                    %
%                                                                    %
%                                                                    %
%                                                                    %
% References:                                                        %
%                                                                    %
% Adapted from C-programs to compute the local linear regression     % 
% smoother, density estimators and the Nadaraya-Watson estimators,   %
% by using direct naive, BINNING, and UPDATING algorithms, which are %
% decribed in the paper                                              %
%       "Fast implementations of nonparametric curve estimators"     %
% by Fan and Marron, 1994, JCGS, vol 3.                              %
% *******************************************************************%

% Check the input data length 
%---------------------------------------------------------------------

if size(data,2) < size(data,1), 
disp('The number of rows for data cannot be greater than its number')
disp('of columns. Now it is not, the program stops.')
return
end

%-------------------------------------------------------------------------
if size(data,1) > 2 
disp('The number of rows for data cannot be greater than 2.')
disp('Now it is not, the program stops.')
return
end

if size(data,1) == 2, imethod=1; end


% To evaluate y's value, called mhat, at the inserted x, defined by nxgrid,
% and range by calling the mex function fest
%-------------------------------------------------------------------------
  output= fest(data,h,range,nxgrid,iker,kpar,imethod,endct);
%-------------------------------------------------------------------------
%see mex.file

% end fastbinsmooth
